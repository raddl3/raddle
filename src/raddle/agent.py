"""Install the bundled provider-neutral acceleration skill into a local project."""

from importlib.resources import files
from importlib.resources.abc import Traversable
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

    def resources(directory: Traversable, prefix: str = "") -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            name = prefix + entry.name
            if entry.is_dir():
                result.update(resources(entry, name + "/"))
            else:
                result[name] = entry.read_bytes()
        return result

    contents = resources(source)
    for name in contents:
        path = folder / name
        if any(part.is_symlink() for part in (path, *path.parents) if part != root):
            raise ValueError(f"refusing to install through a symlink: {path}")
        if any(part.exists() and not part.is_dir() for part in path.parents):
            raise ValueError(f"refusing to replace an installed directory: {path}")
    conflicts = [
        folder / name
        for name, content in contents.items()
        if (folder / name).exists()
        and (not (folder / name).is_file() or (folder / name).read_bytes() != content)
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
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
    action = "Would write" if dry_run else "Wrote"
    details = (
        "\n".join(f"{action}: {path}" for path in written)
        or f"Already installed: {folder}"
    )
    return (
        f"{details}\n\n"
        "Next: inspect a trusted workload with your coding agent or engineer.\n"
        "Review the acceleration plan before candidate work in an isolated worktree.\n"
        "Source and data stay in your environment; no upload to Raddle is required.\n"
        f"\nOptional kickoff prompt:\n{contents['KICKOFF.md'].decode('utf-8')}"
    )
