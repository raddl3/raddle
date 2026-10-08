"""Public command line interface."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from raddle import __version__
from raddle.agent import choose, setup, start
from raddle.agent import init as agent_init
from raddle.artifact import create_artifact
from raddle.contracts import TimingScope
from raddle.cupy_backend import BackendUnavailable
from raddle.preflight import readiness, report
from raddle.registry import get_accelerator, list_accelerators


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="raddle")
    parser.add_argument("--version", action="version", version=f"raddle {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    agent_parser = commands.add_parser("agent", help="Set up a local coding agent")
    agent_commands = agent_parser.add_subparsers(dest="agent_command", required=True)
    init_parser = agent_commands.add_parser("init", help="Install the Raddle skill")
    init_parser.add_argument("--target", type=Path, help="Project root")
    init_parser.add_argument("--agent", choices=("codex", "claude"))
    init_parser.add_argument("--dry-run", action="store_true")
    setup_parser = commands.add_parser(
        "init", help="Configure a coding agent and install the skill"
    )
    setup_parser.add_argument("--target", type=Path, default=Path.cwd())
    setup_parser.add_argument("--agent", choices=("codex", "claude"))
    setup_parser.add_argument("--backend")
    setup_parser.add_argument("--model")
    setup_parser.add_argument("--effort")
    setup_parser.add_argument("--non-interactive", action="store_true")
    setup_parser.add_argument("--reconfigure", action="store_true")
    setup_parser.add_argument("--dry-run", action="store_true")
    start_parser = commands.add_parser(
        "start", help="Launch the configured interactive agent"
    )
    start_parser.add_argument("--target", type=Path, default=Path.cwd())
    start_parser.add_argument("--dry-run", action="store_true")
    doctor = commands.add_parser("doctor", help="Read-only environment readiness")
    doctor.add_argument("--target", type=Path, default=Path.cwd())
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--workload-approved", action="store_true")
    doctor.add_argument("--device")
    doctor.add_argument("--framework", choices=("torch", "onnxruntime", "cupy"))
    doctor.add_argument("--python", type=Path)
    doctor.add_argument("--artifact", action="append", default=[])
    doctor.add_argument("--tool", action="append", default=[])
    doctor.add_argument("--scratch", type=Path)
    doctor.add_argument("--min-free-bytes", type=int, default=0)
    list_parser = commands.add_parser("list", help="List product accelerators")
    list_parser.add_argument("--json", action="store_true")
    inspect_parser = commands.add_parser(
        "inspect", help="Inspect a product accelerator"
    )
    verify_parser = commands.add_parser("verify", help="Validate a canonical case")
    benchmark_parser = commands.add_parser("benchmark", help="Measure a canonical case")
    for command in (inspect_parser, verify_parser, benchmark_parser):
        command.add_argument("accelerator_id")
        command.add_argument("--json", action="store_true")
    for command in (verify_parser, benchmark_parser):
        command.add_argument("--case", required=True)
        command.add_argument("--implementation", default="numpy.vectorized")
    benchmark_parser.add_argument("--repeat", type=int, default=5)
    benchmark_parser.add_argument("--warmup", type=int, default=1)
    benchmark_parser.add_argument(
        "--timing-scope",
        choices=[scope.value for scope in TimingScope],
        default=TimingScope.END_TO_END.value,
    )
    benchmark_parser.add_argument("--baseline", default="python.scalar")
    benchmark_parser.add_argument("--output", type=Path)
    artifact_parser = commands.add_parser(
        "artifact", help="Package a validated orbit fixture with evidence"
    )
    artifact_parser.add_argument("--case", required=True)
    artifact_parser.add_argument("--wheel", required=True, type=Path)
    artifact_parser.add_argument("--output", required=True, type=Path)
    artifact_parser.add_argument("--repeat", type=int, default=3)
    artifact_parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command in ("init", "start", "doctor"):
        try:
            root = args.target.resolve()
            if args.command == "doctor":
                return report(
                    readiness(
                        root,
                        workload_approved=args.workload_approved,
                        device=args.device,
                        framework=args.framework,
                        python=args.python,
                        artifacts=tuple(args.artifact),
                        tools=tuple(args.tool),
                        scratch=args.scratch,
                        min_free_bytes=args.min_free_bytes,
                    ),
                    args.json,
                )
            if args.command == "start":
                checks = readiness(root)
                if any(check.status == "BLOCKED" for check in checks):
                    return report(checks, False)
                return start(root, args.dry_run)
            interactive = not args.non_interactive and sys.stdin.isatty()
            print(
                setup(
                    root,
                    args.agent,
                    args.backend,
                    args.model,
                    args.effort,
                    interactive=interactive,
                    reconfigure=args.reconfigure,
                    dry_run=args.dry_run,
                )
            )
            if not args.dry_run:
                report(readiness(root), False)
            if interactive and not args.dry_run:
                action = choose(
                    "Next action", ["Start guided session", "Exit setup"], "Exit setup"
                )
                if action == "Start guided session":
                    return start(root)
            return 0
        except (ValueError, OSError) as error:
            parser.error(str(error))
    if args.command == "agent":
        try:
            print(agent_init(args.target, args.agent, args.dry_run))
        except ValueError as error:
            parser.error(str(error))
        return 0
    if args.command == "list":
        products = list_accelerators()
        if args.json:
            print(
                json.dumps(
                    [item.to_dict() for item in products],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            for listed in products:
                print(f"{listed.id}  {listed.name}  v{listed.version}")
        return 0
    if args.command == "artifact":
        try:
            create_artifact(
                args.case,
                args.wheel,
                args.output,
                args.repeat,
                args.warmup,
            )
        except (KeyError, OSError, ValueError) as error:
            parser.error(str(error))
        print(args.output / "manifest.json")
        return 0
    try:
        product = get_accelerator(args.accelerator_id)
    except KeyError:
        parser.error(f"unknown accelerator: {args.accelerator_id}")
    if args.command == "inspect":
        descriptor = product.descriptor
        if args.json:
            details = descriptor.to_dict()
            availability = {
                item.id: product.availability(item.id)
                for item in (descriptor.reference, *descriptor.candidates)
            }
            details["availability"] = {
                item.id: {
                    "supported": True,
                    "available_here": availability[item.id][0],
                    "reason": availability[item.id][1],
                }
                for item in (descriptor.reference, *descriptor.candidates)
            }
            print(json.dumps(details, sort_keys=True, separators=(",", ":")))
        else:
            print(f"{descriptor.name} ({descriptor.id}, v{descriptor.version})")
            for implementation in (descriptor.reference, *descriptor.candidates):
                available, reason = product.availability(implementation.id)
                status = (
                    "available here" if available else f"unavailable here: {reason}"
                )
                print(f"{implementation.id}  supported · {status}")
            print(f"Precision: {descriptor.precision}")
            print(f"Validation: {descriptor.validation_policy.id}")
            print("Cases: " + ", ".join(item.id for item in descriptor.cases))
        return 0
    if args.case not in {item.id for item in product.descriptor.cases}:
        parser.error(f"unknown case: {args.case}")
    if args.implementation not in {item.id for item in product.descriptor.candidates}:
        parser.error(f"unknown implementation: {args.implementation}")
    available, reason = product.availability(args.implementation)
    if not available:
        parser.error(
            f"{args.implementation} is supported but unavailable here: {reason}"
        )
    try:
        if args.command == "verify":
            receipt = product.verify(args.case, args.implementation)
            if args.json:
                print(receipt.to_json())
            else:
                print(
                    f"{receipt.accelerator_id} / {receipt.case_id} / "
                    f"{receipt.candidate.id}: {receipt.status}"
                )
                print(f"max abs error {receipt.max_absolute_error:.3g}")
                print(f"max rel error {receipt.max_relative_error:.3g}")
            return 0 if receipt.status == "matched" else 1
        benchmark_receipt = product.benchmark(
            args.case,
            args.repeat,
            args.warmup,
            args.implementation,
            TimingScope(args.timing_scope),
            args.baseline,
        )
        if args.output is not None:
            args.output.write_text(benchmark_receipt.to_json() + "\n", encoding="utf-8")
        if args.json:
            print(benchmark_receipt.to_json())
        else:
            print(f"{benchmark_receipt.accelerator_id} / {benchmark_receipt.case_id}")
            print(f"validation: matched · {benchmark_receipt.timing_scope}")
            print(
                f"{benchmark_receipt.baseline.id} median "
                f"{benchmark_receipt.median_baseline_ns / 1e6:.3f} ms"
            )
            print(
                f"candidate median {benchmark_receipt.median_candidate_ns / 1e6:.3f} ms"
            )
            print(f"candidate: {benchmark_receipt.validation.candidate.id}")
            print(f"baseline/candidate: {benchmark_receipt.speedup:.2f}×")
            print(f"host/device transfers: {benchmark_receipt.host_device_transfers}")
            print(
                f"{benchmark_receipt.repeat} repeats, {benchmark_receipt.warmup} warmup"
            )
        return 0
    except KeyError as error:
        parser.error(f"unknown benchmark baseline or implementation: {error}")
    except BackendUnavailable as error:
        parser.error(str(error))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
