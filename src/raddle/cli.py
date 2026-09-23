"""Public command line interface."""

import argparse
import json
from collections.abc import Sequence

from raddle import __version__
from raddle.fixture import DESCRIPTOR, verify


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="raddle")
    parser.add_argument("--version", action="version", version=f"raddle {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List available accelerators")
    verify_parser = commands.add_parser("verify", help="Validate a fixture accelerator")
    verify_parser.add_argument("accelerator_id", choices=[DESCRIPTOR.id])
    args = parser.parse_args(argv)
    if args.command == "list":
        print(json.dumps([DESCRIPTOR.to_dict()], sort_keys=True, separators=(",", ":")))
        return 0
    receipt = verify()
    print(json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if receipt.validation == "matched" else 1


if __name__ == "__main__":
    raise SystemExit(main())
