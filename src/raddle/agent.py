"""Install the bundled provider-neutral acceleration skill into a local project."""

import json
import os
import re
import shutil
import subprocess  # nosec B404 # intentional native runtime/probe execution
import sys
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
    if agent not in ("codex", "claude"):
        raise ValueError("supported runtimes: codex, claude")
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
        "Next: trace one workload and approve its target before profiling.\n"
        "Review the acceleration plan before candidate work in an isolated worktree.\n"
        "Source and data stay in your environment; no upload to Raddle is required.\n"
        f"\nOptional kickoff prompt:\n{contents['KICKOFF.md'].decode('utf-8')}"
    )


# Runtime configuration stays in the runtime; this file stores launch overrides only.
def config_path(root: Path) -> Path:
    path = root / ".raddle" / "agent.json"
    if any(p.is_symlink() for p in (path, *path.parents) if p != root):
        raise ValueError("refusing agent configuration through a symlink")
    return path


def discover() -> list[str]:
    return [name for name in ("codex", "claude") if shutil.which(name)]


def runtime_help(agent: str) -> str:
    binary = shutil.which(agent)
    if binary is None:
        raise ValueError(
            f"{agent} is unavailable; install it and authenticate separately"
        )
    try:
        result = subprocess.run(  # nosec B603 # fixed flags, argv list, no shell
            [binary, "--help"], capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"cannot inspect {agent}; run {agent} --help") from error
    return result.stdout


def models(agent: str) -> dict[str, list[str]]:
    """Read Codex's own cached catalog; never invent model identifiers."""
    if agent != "codex":
        return {}
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    try:
        catalog = json.loads((home / "models_cache.json").read_text())
        return {
            item["slug"]: [
                level["effort"] for level in item["supported_reasoning_levels"]
            ]
            for item in catalog["models"]
            if item.get("visibility") == "list"
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def validate_config(config: object, *, capabilities: bool = True) -> dict[str, str]:
    if not isinstance(config, dict) or set(config) != {
        "agent",
        "backend",
        "model",
        "effort",
    }:
        raise ValueError("invalid .raddle/agent.json; review before rerunning init")
    if any(not isinstance(value, str) for value in config.values()):
        raise ValueError("agent configuration values must be strings")
    result: dict[str, str] = dict(config)
    agent, backend, model, effort = (
        result[k] for k in ("agent", "backend", "model", "effort")
    )
    if agent not in ("codex", "claude"):
        raise ValueError("supported runtimes: codex, claude")
    if backend != "default":
        raise ValueError(
            f"{agent}/{backend} is unsupported in v0.6.0; configure your runtime "
            "backend separately and select default to inherit it"
        )
    if model and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model) is None:
        raise ValueError(
            "invalid model identifier; secrets and options are not allowed"
        )
    if effort not in ("", "low", "medium", "high"):
        raise ValueError("supported effort overrides: low, medium, high")
    if capabilities:
        help_text = runtime_help(agent)
        if model and ("--model" not in help_text or model not in models(agent)):
            raise ValueError(
                "model is not verified by the runtime catalog; select runtime default. "
                "Claude overrides and uncatalogued provider models are unsupported"
            )
        if effort:
            if agent == "codex":
                if (
                    "--config" not in help_text
                    or not model
                    or effort not in models(agent).get(model, [])
                ):
                    raise ValueError(
                        "Codex effort requires a supporting catalogued model"
                    )
            elif "--effort" not in help_text:
                raise ValueError("this Claude runtime does not support --effort")
    return result


def read_config(root: Path, *, capabilities: bool = True) -> dict[str, str]:
    try:
        data = json.loads(config_path(root).read_text())
    except (OSError, ValueError) as error:
        raise ValueError("agent configuration unavailable; run raddle init") from error
    return validate_config(data, capabilities=capabilities)


def choose(label: str, options: list[str], default: str) -> str:
    print(label + ":")
    for number, option in enumerate(options, 1):
        print(f"  {number}. {option}" + (" (default)" if option == default else ""))
    while True:
        answer = input("Choice [Enter for default]: ").strip()
        if not answer:
            return default
        if answer in options:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print("Choose a listed option.")


def setup(
    root: Path,
    agent: str | None,
    backend: str | None,
    model: str | None,
    effort: str | None,
    *,
    interactive: bool,
    reconfigure: bool,
    dry_run: bool,
) -> str:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("project directory is unavailable")
    path = config_path(root)
    old = read_config(root, capabilities=False) if path.exists() else None
    if interactive:
        print("Welcome to Raddle.\nLet's connect your coding agent.")
        available = discover()
        if not available:
            raise ValueError("no supported runtime found; install Codex or Claude Code")
        agent = agent or choose(
            "Agent runtime",
            available,
            old["agent"] if old and old["agent"] in available else available[0],
        )
        backend = backend or choose("Model backend", ["default"], "default")
        print(
            "Default inherits your runtime backend and "
            "authentication. New routing is unsupported."
        )
        if model is None:
            catalog = models(agent)
            selected = choose(
                "Model (runtime catalog; availability depends on your backend)",
                ["default", *catalog],
                old["model"]
                if old and old["agent"] == agent and old["model"] in catalog
                else "default",
            )
            model = "" if selected == "default" else selected
        if effort is None:
            supported_efforts = (
                ["low", "medium", "high"]
                if agent == "claude" and "--effort" in runtime_help(agent)
                else models(agent).get(model or "", [])
            )
            options = [
                "default",
                *[e for e in ("low", "medium", "high") if e in supported_efforts],
            ]
            selected = choose(
                "Reasoning effort",
                options,
                old["effort"]
                if old and old["agent"] == agent and old["effort"] in options
                else "default",
            )
            effort = "" if selected == "default" else selected
    elif agent is None:
        agent = old["agent"] if old else None
        if agent is None:
            raise ValueError(
                "noninteractive setup requires --agent codex or --agent claude"
            )
    config_data = {
        "agent": agent,
        "backend": backend or "default",
        "model": "" if model == "default" else model or "",
        "effort": "" if effort == "default" else effort or "",
    }
    if old is not None and not interactive:
        for key, override in [
            ("backend", backend),
            ("model", model),
            ("effort", effort),
        ]:
            if override is None and agent == old["agent"]:
                config_data[key] = old[key]
    config = validate_config(config_data)
    if old is not None and config != old and not reconfigure:
        raise ValueError(
            "configuration differs; review .raddle/agent.json and pass --reconfigure"
        )
    temporary = path.with_suffix(".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(
            "configuration temporary file already exists; review it before retrying"
        )
    # The existing installer preflights every conflict before any write.
    installation = init(root, config["agent"], dry_run)
    if not dry_run and config != old:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        temporary.replace(path)
    return (
        installation.split("\n\n")[0]
        + ("\nWould configure agent." if dry_run else "\nConfiguration complete.")
        + " Next: raddle doctor, then raddle start."
    )


def launch_command(root: Path, config: dict[str, str]) -> list[str]:
    config = validate_config(config)
    agent = config["agent"]
    binary = shutil.which(agent)
    if binary is None:
        raise ValueError("configured runtime disappeared from PATH; run raddle doctor")
    folder = (
        root
        / (".agents" if agent == "codex" else ".claude")
        / "skills/raddle-accelerate"
    )
    if not (folder / "SKILL.md").is_file():
        raise ValueError("Raddle skill missing; run raddle init")
    prompt = (folder / "KICKOFF.md").read_text(encoding="utf-8")
    command = [binary]
    if config["model"]:
        command += ["--model", config["model"]]
    if config["effort"]:
        command += (
            ["--config", "model_reasoning_effort=" + json.dumps(config["effort"])]
            if agent == "codex"
            else ["--effort", config["effort"]]
        )
    return [*command, prompt]


def start(root: Path, dry_run: bool = False) -> int:
    command = launch_command(root, read_config(root))
    if dry_run:
        print(json.dumps({"cwd": str(root), "argv": command}, indent=2))
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError(
            "raddle start requires an interactive terminal; use --dry-run to inspect"
        )
    return subprocess.call(command, cwd=root)  # nosec B603 # verified argv, no shell
