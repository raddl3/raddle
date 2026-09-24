import json
import math
from dataclasses import replace

import numpy as np
import pytest
from numpy.typing import NDArray
from pytest import CaptureFixture, MonkeyPatch

from raddle import __version__
from raddle.cli import main
from raddle.contracts import BenchmarkReceipt, ValidationReceipt
from raddle.orbit import (
    DESCRIPTOR,
    PropagationInput,
    accelerated,
    benchmark,
    case,
    reference,
    validate,
    verify,
)
from raddle.registry import get_accelerator, list_accelerators


def test_registry_and_descriptor() -> None:
    assert [item.id for item in list_accelerators()] == ["orbit.two_body_rk4"]
    assert get_accelerator(DESCRIPTOR.id).descriptor is DESCRIPTOR
    with pytest.raises(KeyError):
        get_accelerator("fixture.sum_squares")
    assert DESCRIPTOR.reference.id == "python.scalar"
    assert DESCRIPTOR.candidate.id == "numpy.vectorized"
    assert [item.id for item in DESCRIPTOR.cases] == [
        "circular.small",
        "batch.standard",
    ]
    assert DESCRIPTOR.to_json() == DESCRIPTOR.to_json()
    assert json.loads(DESCRIPTOR.to_json())["precision"] == "float64"


def test_cases_are_deterministic_and_independent() -> None:
    for definition in DESCRIPTOR.cases:
        first = case(definition.id)
        second = case(definition.id)
        np.testing.assert_array_equal(first.initial_states, second.initial_states)
        assert np.asarray(first.initial_states).shape == (definition.trajectories, 6)
        assert first.steps == definition.steps
    with pytest.raises(KeyError):
        case("missing")


def test_scalar_vectorized_agreement_and_receipt() -> None:
    inputs = case("circular.small")
    expected = reference(inputs)
    actual = accelerated(inputs)
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-11)
    receipt = verify("circular.small")
    assert isinstance(receipt, ValidationReceipt)
    assert receipt.status == "matched"
    assert receipt.compared_values == 24
    assert receipt.policy.id == "float64.state_elementwise.v1"
    assert json.loads(receipt.to_json())["status"] == "matched"
    assert receipt.to_json() == receipt.to_json()


def test_deliberate_perturbation_fails_validation() -> None:
    expected = reference(case("circular.small"))
    changed = expected.copy()
    changed[0, 0] += 1e-5
    receipt = validate("circular.small", expected, changed)
    assert receipt.status == "mismatched"
    assert receipt.max_absolute_error >= 1e-5 - 1e-12


@pytest.mark.parametrize(
    ("states", "mu", "dt", "steps"),
    [
        ([], 1.0, 0.1, 1),
        ([[1.0] * 5], 1.0, 0.1, 1),
        ([[0.0] * 6], 1.0, 0.1, 1),
        ([[math.nan, 0, 0, 0, 1, 0]], 1.0, 0.1, 1),
        ([[1, 0, 0, 0, 1, 0]], 0.0, 0.1, 1),
        ([[1, 0, 0, 0, 1, 0]], 1.0, math.inf, 1),
        ([[1, 0, 0, 0, 1, 0]], 1.0, -0.1, 1),
        ([[1, 0, 0, 0, 1, 0]], 1.0, 0.1, 0),
        ([[1, 0, 0, 0, 1, 0]], 1.0, 0.1, True),
    ],
)
def test_invalid_inputs(states: object, mu: float, dt: float, steps: int) -> None:
    with pytest.raises(ValueError):
        PropagationInput(states, mu, dt, steps)  # type: ignore[arg-type]


def test_circular_orbit_physical_sanity() -> None:
    inputs = case("circular.small")
    initial = np.asarray(inputs.initial_states)
    for implementation in (reference, accelerated):
        final = implementation(inputs)
        # A full revolution at r=1 should approximately return to the start.
        np.testing.assert_allclose(final[0], initial[0], rtol=0, atol=2e-7)
        initial_energy = np.sum(
            initial[:, 3:] ** 2, axis=1
        ) / 2 - inputs.mu / np.linalg.norm(initial[:, :3], axis=1)
        final_energy = np.sum(
            final[:, 3:] ** 2, axis=1
        ) / 2 - inputs.mu / np.linalg.norm(final[:, :3], axis=1)
        np.testing.assert_allclose(final_energy, initial_energy, rtol=0, atol=2e-7)


def test_benchmark_receipt_and_private_provenance() -> None:
    receipt = benchmark("circular.small", repeat=2, warmup=0)
    assert isinstance(receipt, BenchmarkReceipt)
    assert receipt.schema_version == receipt.validation.schema_version == 1
    assert receipt.validation.status == "matched"
    assert len(receipt.reference_times_ns) == len(receipt.candidate_times_ns) == 2
    assert all(
        value > 0 for value in receipt.reference_times_ns + receipt.candidate_times_ns
    )
    assert receipt.speedup > 0
    data = json.loads(receipt.to_json())
    assert data["clock"] == "perf_counter_ns"
    assert data["median_reference_ns"] == receipt.median_reference_ns
    with pytest.raises(ValueError, match="matched validation"):
        replace(receipt, validation=replace(receipt.validation, status="mismatched"))
    for forbidden in ("hostname", "username", "home", "path", "environment", "secret"):
        assert forbidden not in receipt.to_json().lower()


def test_cli(capsys: CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert "orbit.two_body_rk4" in capsys.readouterr().out
    assert main(["list", "--json"]) == 0
    assert [item["id"] for item in json.loads(capsys.readouterr().out)] == [
        DESCRIPTOR.id
    ]
    assert main(["inspect", DESCRIPTOR.id, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["candidate"]["id"] == "numpy.vectorized"
    assert main(["verify", DESCRIPTOR.id, "--case", "circular.small", "--json"]) == 0
    first_verify = capsys.readouterr().out
    assert json.loads(first_verify)["status"] == "matched"
    assert main(["verify", DESCRIPTOR.id, "--case", "circular.small", "--json"]) == 0
    assert capsys.readouterr().out == first_verify
    assert (
        main(
            [
                "benchmark",
                DESCRIPTOR.id,
                "--case",
                "circular.small",
                "--repeat",
                "1",
                "--warmup",
                "0",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["validation"]["status"] == "matched"
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"raddle {__version__}"


def test_cli_mismatch(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    original = accelerated

    def changed(inputs: PropagationInput) -> NDArray[np.float64]:
        output = original(inputs)
        output[0, 0] += 1e-5
        return output

    monkeypatch.setattr("raddle.orbit.accelerated", changed)
    assert main(["verify", DESCRIPTOR.id, "--case", "circular.small", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "mismatched"
    with pytest.raises(ValueError, match="benchmark validation failed"):
        benchmark("circular.small", repeat=1, warmup=0)


def test_benchmark_arguments_and_intermediate_singularity() -> None:
    with pytest.raises(ValueError, match="repeat"):
        benchmark("circular.small", repeat=0)
    with pytest.raises(ValueError, match="warmup"):
        benchmark("circular.small", repeat=1, warmup=-1)
    singular = PropagationInput([[1, 0, 0, -2, 0, 0]], mu=1, dt=1, steps=1)
    for implementation in (reference, accelerated):
        with pytest.raises(ValueError, match="singular"):
            implementation(singular)
