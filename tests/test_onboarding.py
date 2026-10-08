"""Agent boundaries without paid model calls or application execution."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from raddle import agent, preflight
from raddle.cli import main


@pytest.fixture
def runtime(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "raddle.agent.shutil.which",
        lambda name: "/mock/" + name if name in ("codex", "claude", "uv") else None,
    )
    monkeypatch.setattr(agent, "runtime_help", lambda name: "--model --config --effort")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "models_cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "test-model",
                        "visibility": "list",
                        "supported_reasoning_levels": [{"effort": "high"}],
                    }
                ]
            }
        )
    )


def setup(root: Path, **kwargs: object) -> int:
    flags = ["init", "--target", str(root), "--agent", "codex", "--non-interactive"]
    for key, value in kwargs.items():
        flags.append("--" + key.replace("_", "-"))
        if isinstance(value, str):
            flags.append(value)
    return main(flags)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_setup_repeat_reconfigure_and_protection(tmp_path: Path, runtime: None) -> None:
    assert setup(tmp_path, model="test-model", effort="high") == 0
    before = snapshot(tmp_path)
    assert setup(tmp_path) == 0
    assert snapshot(tmp_path) == before
    with pytest.raises(SystemExit):
        setup(tmp_path, model="default")
    assert snapshot(tmp_path) == before
    assert setup(tmp_path, model="default", effort="default", reconfigure=True) == 0
    skill = tmp_path / ".agents/skills/raddle-accelerate/SKILL.md"
    skill.write_text("user changes")
    before = snapshot(tmp_path)
    with pytest.raises(SystemExit):
        setup(tmp_path, reconfigure=True)
    assert snapshot(tmp_path) == before


def test_interactive_setup(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    answers = iter(["codex", "default", "test-model", "high", "Exit setup"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert main(["init", "--target", str(tmp_path)]) == 0
    assert agent.read_config(tmp_path)["model"] == "test-model"


@pytest.mark.parametrize(
    "flags",
    [
        {"backend": "openrouter"},
        {"backend": "ollama"},
        {"backend": "lmstudio"},
        {"model": "GPT-6.1-sol"},
        {"model": "--dangerously-bypass-approvals-and-sandbox"},
        {"model": "$(touch injected)"},
        {"effort": "high"},
        {"effort": "ultra"},
    ],
)
def test_unsupported_before_writes(
    tmp_path: Path, runtime: None, flags: dict[str, str]
) -> None:
    with pytest.raises(SystemExit):
        setup(tmp_path, **flags)
    assert not (tmp_path / ".raddle").exists()
    assert not (tmp_path / ".agents").exists()


def test_claude_and_capabilities(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    assert (
        main(
            [
                "init",
                "--target",
                str(tmp_path),
                "--agent",
                "claude",
                "--effort",
                "low",
                "--non-interactive",
            ]
        )
        == 0
    )
    command = agent.launch_command(tmp_path, agent.read_config(tmp_path))
    assert command[:3] == ["/mock/claude", "--effort", "low"]
    with pytest.raises(ValueError, match="not verified"):
        agent.validate_config(
            {
                "agent": "claude",
                "backend": "default",
                "model": "test-model",
                "effort": "",
            }
        )
    monkeypatch.setattr(agent, "runtime_help", lambda name: "--model")
    with pytest.raises(ValueError, match="does not support"):
        agent.read_config(tmp_path)


def test_secure_launch_and_dry_run(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    assert setup(tmp_path, model="test-model", effort="high") == 0
    config = agent.read_config(tmp_path)
    command = agent.launch_command(tmp_path, config)
    assert command[:5] == [
        "/mock/codex",
        "--model",
        "test-model",
        "--config",
        'model_reasoning_effort="high"',
    ]
    assert "--sandbox" not in command and "--ask-for-approval" not in command
    assert "Welcome me briefly" in command[-1]
    assert main(["start", "--target", str(tmp_path), "--dry-run"]) == 0
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    calls: list[tuple[list[str], Path]] = []

    def launch(argv: list[str], *, cwd: Path) -> int:
        calls.append((argv, cwd))
        return 7

    monkeypatch.setattr("raddle.agent.subprocess.call", launch)
    assert main(["start", "--target", str(tmp_path)]) == 7
    assert calls == [(command, tmp_path)]
    path = agent.config_path(tmp_path)
    path.write_text(json.dumps(config | {"api_key": "secret"}))
    with pytest.raises(ValueError, match="invalid"):
        agent.read_config(tmp_path)


def test_dry_run_and_symlink_config(tmp_path: Path, runtime: None) -> None:
    assert setup(tmp_path, dry_run=True) == 0
    assert not (tmp_path / ".raddle").exists()
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / ".raddle").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(SystemExit):
        setup(tmp_path)
    assert not list((tmp_path / "elsewhere").iterdir())


def test_cpu_readiness_no_mutation(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    setup(tmp_path)
    before = snapshot(tmp_path)

    def forbidden(argv: list[str], root: Path) -> str:
        raise AssertionError("CPU checks must not invoke GPU or application probes")

    monkeypatch.setattr(preflight, "run_probe", forbidden)
    checks = preflight.readiness(
        tmp_path, workload_approved=True, device="cpu", tools=("uv",), min_free_bytes=1
    )
    assert not any(c.status == "BLOCKED" for c in checks)
    assert any(c.status == "WARN" for c in checks)  # no Git worktree
    assert any(c.status == "NOT CHECKED" for c in checks)
    assert any(c.status == "PASS" for c in checks)
    assert snapshot(tmp_path) == before
    assert main(["doctor", "--target", str(tmp_path), "--json"]) == 0


def test_artifacts_gpu_and_permissions(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    setup(tmp_path)
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"fixture")
    digest = hashlib.sha256(b"fixture").hexdigest()
    before = snapshot(tmp_path)
    checks = preflight.readiness(
        tmp_path,
        workload_approved=True,
        device="cuda:0",
        artifacts=("model.bin=" + digest,),
        tools=("missing-tool",),
        min_free_bytes=10**30,
    )
    states = {c.name: c.status for c in checks}
    assert states["GPU driver"] == "BLOCKED"
    assert states["artifact model.bin"] == "PASS"
    assert states["tool missing-tool"] == states["scratch storage"] == "BLOCKED"
    assert snapshot(tmp_path) == before
    monkeypatch.setattr(preflight, "accessible", lambda path: False)
    checks = preflight.readiness(tmp_path)
    assert (
        next(c for c in checks if c.name == "workspace permissions").status == "BLOCKED"
    )
    with pytest.raises(ValueError, match="target approval"):
        preflight.readiness(tmp_path, device="cuda:0")
    with pytest.raises(ValueError, match="boundary"):
        preflight.readiness(
            tmp_path, workload_approved=True, artifacts=("../outside=" + digest,)
        )
    checks = preflight.readiness(
        tmp_path, workload_approved=True, artifacts=("model.bin=" + "0" * 64,)
    )
    assert next(c for c in checks if c.name == "artifact model.bin").status == "BLOCKED"


def test_framework_probe_is_bounded_and_specific(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    setup(tmp_path)
    calls: list[list[str]] = []

    def probe(argv: list[str], root: Path) -> str:
        calls.append(argv)
        return '{"providers": ["CPUExecutionProvider"]}'

    monkeypatch.setattr(preflight, "run_probe", probe)
    checks = preflight.readiness(
        tmp_path,
        workload_approved=True,
        device="cuda:0",
        framework="onnxruntime",
        python=Path("/trusted/python"),
    )
    assert next(c for c in checks if c.name == "framework").status == "BLOCKED"
    assert calls[0][:4] == ["/trusted/python", "-I", "-B", "-c"]
    assert "get_available_providers" in calls[0][-1]
    assert "InferenceSession" not in calls[0][-1]
    checks = preflight.readiness(
        tmp_path, workload_approved=True, device="cpu", framework="onnxruntime"
    )
    assert next(c for c in checks if c.name == "framework").status == "NOT CHECKED"


def test_approval_protocol_is_capability_aware(tmp_path: Path) -> None:
    agent.init(tmp_path, "codex")
    skill = (tmp_path / ".agents/skills/raddle-accelerate/SKILL.md").read_text()
    assert "target, plan, adoption and another-loop approval" in skill
    assert "tools actually\navailable in this interaction mode" in skill
    assert "tool call fails, ask conversationally" in skill
    assert "**Approve / Request changes / Decline**" in skill
    assert "empty/tool error response, and ambiguous replies are not approval" in skill
    assert "revise the proposal and STOP for\n  fresh approval" in skill
    assert "Changes never authorize execution" in skill
    assert "stop the proposed action cleanly" in skill
    assert "Do not discard previous results" in skill
    assert "BLOCKED stops the affected" in skill


def test_interactive_repeat_preserves_overrides(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    setup(tmp_path, model="test-model", effort="high")
    before = snapshot(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert main(["init", "--target", str(tmp_path)]) == 0
    assert snapshot(tmp_path) == before


def test_missing_runtime_and_catalog(
    tmp_path: Path, runtime: None, monkeypatch: MonkeyPatch
) -> None:
    home = Path(os.environ["CODEX_HOME"])
    (home / "models_cache.json").write_text('{"models": [null]}')
    assert agent.models("codex") == {}
    with pytest.raises(SystemExit):
        setup(tmp_path, model="test-model")


def test_runtime_missing(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("raddle.agent.shutil.which", lambda name: None)
    assert agent.discover() == []
    with pytest.raises(ValueError, match="unavailable"):
        agent.runtime_help("codex")
