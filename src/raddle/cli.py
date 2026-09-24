"""Public command line interface."""

import argparse
import json
from collections.abc import Sequence

from raddle import __version__
from raddle.contracts import TimingScope
from raddle.cupy_backend import BackendUnavailable
from raddle.registry import get_accelerator, list_accelerators


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="raddle")
    parser.add_argument("--version", action="version", version=f"raddle {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
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
    args = parser.parse_args(argv)
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
