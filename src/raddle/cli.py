"""Public command line interface."""

import argparse
import json
from collections.abc import Sequence

from raddle import __version__
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
    benchmark_parser.add_argument("--repeat", type=int, default=5)
    benchmark_parser.add_argument("--warmup", type=int, default=1)
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
            for item in products:
                print(f"{item.id}  {item.name}  v{item.version}")
        return 0
    try:
        product = get_accelerator(args.accelerator_id)
    except KeyError:
        parser.error(f"unknown accelerator: {args.accelerator_id}")
    if args.command == "inspect":
        descriptor = product.descriptor
        if args.json:
            print(descriptor.to_json())
        else:
            print(f"{descriptor.name} ({descriptor.id}, v{descriptor.version})")
            print(f"{descriptor.reference.id} → {descriptor.candidate.id}")
            print(f"Precision: {descriptor.precision}")
            print(f"Validation: {descriptor.validation_policy.id}")
            print("Cases: " + ", ".join(item.id for item in descriptor.cases))
        return 0
    try:
        if args.command == "verify":
            receipt = product.verify(args.case)
            if args.json:
                print(receipt.to_json())
            else:
                print(f"{receipt.accelerator_id} / {receipt.case_id}: {receipt.status}")
                print(f"max abs error {receipt.max_absolute_error:.3g}")
                print(f"max rel error {receipt.max_relative_error:.3g}")
            return 0 if receipt.status == "matched" else 1
        benchmark_receipt = product.benchmark(args.case, args.repeat, args.warmup)
        if args.json:
            print(benchmark_receipt.to_json())
        else:
            print(f"{benchmark_receipt.accelerator_id} / {benchmark_receipt.case_id}")
            print("validation: matched")
            print(
                f"reference median {benchmark_receipt.median_reference_ns / 1e6:.3f} ms"
            )
            print(
                f"candidate median {benchmark_receipt.median_candidate_ns / 1e6:.3f} ms"
            )
            print(f"speedup {benchmark_receipt.speedup:.2f}×")
            print(
                f"{benchmark_receipt.repeat} repeats, {benchmark_receipt.warmup} warmup"
            )
        return 0
    except KeyError:
        parser.error(f"unknown case: {args.case}")
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
