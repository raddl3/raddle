from pathlib import Path

import pytest
from pytest import MonkeyPatch

from raddle.agent import init
from raddle.cli import main


def test_agent_init_safe_idempotent_and_prompt(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='example'\n")
    source = project / "app.py"
    source.write_text("print('untouched')\n")
    nested = project / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)
    folder = project / ".agents/skills/raddle-accelerate"
    preview = init(None, None, True)
    assert "Would write" in preview and not folder.exists()
    first = init(None, None)
    assert "Wrote:" in first
    assert (folder / "SKILL.md").read_text().startswith("---\nname: raddle-accelerate")
    assert "Profile the existing project" in (folder / "KICKOFF.md").read_text()
    skill = (folder / "SKILL.md").read_text()
    prompt = (folder / "KICKOFF.md").read_text()
    assert "stop for review" in skill
    assert "isolated Git worktree" in prompt
    assert "unmeasured" in prompt
    assert "Forge validation gate before benchmarking" in prompt
    assert "Next: inspect a trusted workload" in first
    assert "no upload to Raddle is required" in first
    assert first.endswith((folder / "KICKOFF.md").read_text())
    assert "Already installed" in init(None, None)
    assert source.read_text() == "print('untouched')\n"
    (folder / "SKILL.md").write_text("my custom skill")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        init(None, None)
    assert (folder / "SKILL.md").read_text() == "my custom skill"


def test_agent_init_ambiguous_target(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["agent", "init", "--target", str(tmp_path), "--dry-run"]) == 0
    assert not (tmp_path / ".agents").exists()
    with pytest.raises(ValueError, match="project root is ambiguous"):
        init(None, None)
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".claude").mkdir()
    with pytest.raises(ValueError, match="agent target is ambiguous"):
        init(None, None)
    result = init(tmp_path, "claude")
    assert str(tmp_path / ".claude/skills/raddle-accelerate/SKILL.md") in result


@pytest.mark.parametrize(
    "agent, directory", [("codex", ".agents"), ("claude", ".claude")]
)
def test_recursive_install_preflights_all_conflicts(
    tmp_path: Path, agent: str, directory: str
) -> None:
    folder = tmp_path / directory / "skills/raddle-accelerate"
    init(tmp_path, agent, True)
    assert not folder.exists()
    init(tmp_path, agent)
    reference = folder / "references/external-workload.md"
    assert reference.is_file()
    assert (folder / "references/artifacts.md").is_file()
    assert (folder / "references/evaluation.md").is_file()
    reference.write_text("my adapter instructions")
    (folder / "KICKOFF.md").unlink()
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="refusing to overwrite"):
            init(tmp_path, agent, dry_run)
        assert not (folder / "KICKOFF.md").exists()
        assert reference.read_text() == "my adapter instructions"


def test_install_refuses_symlink_destination(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        init(tmp_path, "codex")
    assert not list(outside.iterdir())


def test_install_preflights_directory_conflict(tmp_path: Path) -> None:
    folder = tmp_path / ".agents/skills/raddle-accelerate"
    folder.mkdir(parents=True)
    (folder / "references").write_text("user-owned file")
    with pytest.raises(ValueError, match="installed directory"):
        init(tmp_path, "codex")
    assert not (folder / "SKILL.md").exists()
    assert (folder / "references").read_text() == "user-owned file"
