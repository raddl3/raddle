"""Install the bundled provider-neutral acceleration skill into a local project."""

from importlib.resources import files
from pathlib import Path


def project_root(start: Path) -> Path:
    for path in (start.resolve(), *start.resolve().parents):
        if any(
            (path / marker).exists()
            for marker in (".git", "pyproject.toml", "package.json")
        ):
            return path
    raise ValueError("project root is ambiguous; pass --target PROJECT_ROOT")


def init(target: Path | None, agent: str | None, dry_run: bool = False) -> str:
    root = project_root(Path.cwd()) if target is None else target.resolve()
    if not root.is_dir():
        raise ValueError(f"target is not a directory: {root}")
    if agent is None:
        codex = (root / ".agents").exists() or (root / ".codex").exists()
        claude = (root / ".claude").exists()
        if codex and claude:
            raise ValueError(
                "agent target is ambiguous; pass --agent codex or --agent claude"
            )
        agent = "claude" if claude else "codex"
    folder = (
        root
        / (".agents" if agent == "codex" else ".claude")
        / "skills"
        / "raddle-accelerate"
    )
    source = files("raddle").joinpath("skills", "raddle-accelerate")
    contents = {
        name: source.joinpath(name).read_text(encoding="utf-8")
        for name in ("SKILL.md", "KICKOFF.md")
    }
    conflicts = [
        folder / name
        for name, content in contents.items()
        if (folder / name).exists()
        and (folder / name).read_text(encoding="utf-8") != content
    ]
    if conflicts:
        raise ValueError(
            "refusing to overwrite modified file(s): " + ", ".join(map(str, conflicts))
        )
    written = []
    for name, content in contents.items():
        path = folder / name
        if not path.exists():
            written.append(path)
            if not dry_run:
                folder.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    action = "Would write" if dry_run else "Wrote"
    details = (
        "\n".join(f"{action}: {path}" for path in written)
        or f"Already installed: {folder}"
    )
    return f"{details}\n\nKickoff prompt:\n{contents['KICKOFF.md']}"
