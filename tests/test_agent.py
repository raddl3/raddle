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
