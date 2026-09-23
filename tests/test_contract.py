import json

import pytest
from pytest import CaptureFixture, MonkeyPatch

from raddle import __version__
from raddle.cli import main
from raddle.contracts import ValidationReceipt
from raddle.fixture import DESCRIPTOR, accelerated, reference, verify


def test_fixture_contract_and_receipt() -> None:
    assert DESCRIPTOR.to_dict()["id"] == "fixture.sum_squares"
    assert reference((1, 2, 3, 4)) == accelerated((1, 2, 3, 4)) == 30
    receipt = verify()
    assert isinstance(receipt, ValidationReceipt)
    assert receipt.validation == "matched"
    assert receipt.reference_result == receipt.accelerated_result == 30
    assert json.loads(json.dumps(receipt.to_dict())) == receipt.to_dict()


def test_cli_output_is_deterministic(capsys: CaptureFixture[str]) -> None:
    assert main(["verify", DESCRIPTOR.id]) == 0
    first = capsys.readouterr().out
    assert main(["verify", DESCRIPTOR.id]) == 0
    assert capsys.readouterr().out == first
    assert json.loads(first)["validation"] == "matched"


def test_mismatch_fails_validation(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr("raddle.fixture.accelerated", lambda values: -1)
    assert main(["verify", DESCRIPTOR.id]) == 1
    assert json.loads(capsys.readouterr().out)["validation"] == "mismatched"


def test_list_and_version(capsys: CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == DESCRIPTOR.id
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"raddle {__version__}"
