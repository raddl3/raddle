import hashlib
import itertools
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pytest import CaptureFixture, MonkeyPatch

from raddle.bootstrap import (
    ALGORITHM,
    BootstrapInput,
    accelerated,
    benchmark,
    case,
    plans,
    reference,
    validate,
    verify,
)
from raddle.cli import main
from raddle.evidence import check_receipt, read_receipt


def test_independent_semantics_and_chunk_invariance(monkeypatch: MonkeyPatch) -> None:
    inputs = BootstrapInput([0.0, 2.0], 100, 17, 0.8)
    expected = reference(inputs)
    actual = accelerated(inputs)
    np.testing.assert_allclose(
        actual.distribution, expected.distribution, rtol=0, atol=1e-12
    )
    assert expected.original_statistic == 1
    assert expected.confidence_level == 0.8
    assert expected.percentile_interval[0] <= expected.percentile_interval[1]
    assert set(expected.distribution) <= {0.0, 1.0, 2.0}
    assert len(set(expected.distribution)) == 3
    assert sum(len(chunk) for chunk in plans(inputs)) == 100
    original_plan = np.concatenate(list(plans(inputs)))
    monkeypatch.setattr("raddle.bootstrap.CHUNK_INDICES", 2)
    np.testing.assert_array_equal(np.concatenate(list(plans(inputs))), original_plan)
    monkeypatch.setattr("raddle.bootstrap.CHUNK_INDICES", 1_048_576)
    constant = reference(BootstrapInput([4.0, 4.0, 4.0], 20, 3, 0.95))
    assert constant.standard_error == 0
    assert constant.percentile_interval == (4.0, 4.0)
    assert set(constant.distribution) == {4.0}
    assert ALGORITHM == "splitmix64.counter_reject.v1"
    zero_seed = (-0x9E3779B97F4A7C15) % (1 << 64)
    assert next(plans(BootstrapInput([1.0, 2.0, 3.0], 2, zero_seed, 0.95)))[0, 0] == 1
    # This seed makes the first mixed uint64 equal 1, which size 10 rejects.
    assert (
        next(plans(BootstrapInput(np.arange(10), 2, 0xF8364607E9C949BD, 0.95)))[0, 0]
        == 9
    )
    # Every possible two-draw outcome has the expected arithmetic mean.
    assert sorted(sum(x) / 2 for x in itertools.product((0.0, 2.0), repeat=2)) == [
        0.0,
        1.0,
        1.0,
        2.0,
    ]


def test_input_validation_and_receipts(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    for sample, resamples, seed, level in (
        ([], 2, 0, 0.95),
        ([[1.0]], 2, 0, 0.95),
        ([float("nan")], 2, 0, 0.95),
        ([1.0], 1, 0, 0.95),
        ([1.0], 2, -1, 0.95),
        ([1.0], 2, 0, 1.0),
    ):
        with pytest.raises(ValueError):
            BootstrapInput(sample, resamples, seed, level)
    with pytest.raises(ValueError, match="finite"):
        reference(BootstrapInput([1e308, 1e308], 2, 0, 0.95))
    small = case("bootstrap.small")
    assert np.asarray(small.sample).tolist() == [0.0, 0.5, 1.0]
    assert next(plans(small))[:5].tolist() == [
        [0, 1, 1],
        [1, 0, 0],
        [1, 2, 2],
        [2, 0, 1],
        [0, 0, 1],
    ]
    np.testing.assert_allclose(
        reference(small).distribution[:5], [1 / 3, 1 / 6, 5 / 6, 1 / 2, 1 / 6]
    )
    assert verify("bootstrap.small").status == "matched"
    mismatch = replace(accelerated(small), distribution=np.full(20, 9.0))
    assert (
        validate("bootstrap.small", reference(small), mismatch).status == "mismatched"
    )
    receipt = benchmark("bootstrap.small", repeat=2, warmup=0)
    assert receipt.validation.status == "matched"
    assert receipt.workload["seed"] == 7
    assert receipt.schema_version == 3
    path = tmp_path / "receipt.json"
    assert (
        main(
            [
                "benchmark",
                "stats.bootstrap",
                "--case",
                "bootstrap.small",
                "--repeat",
                "1",
                "--warmup",
                "0",
                "--output",
                str(path),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == read_receipt(path)
    changed = json.loads(path.read_text())
    changed["speedup"] = 999
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="digest"):
        read_receipt(path)
    changed = json.loads(receipt.to_json())
    changed["validation"]["status"] = "mismatched"
    payload = {key: value for key, value in changed.items() if key != "content_sha256"}
    changed["content_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="validation must match"):
        check_receipt(changed)
