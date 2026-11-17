"""Command line: python -m blastledger assess fixtures/danger.json"""
import argparse
import json
from pathlib import Path
import sys

from .engine import InputError, assess


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only BlastLedger change risk evaluation")
    parser.add_argument("command", choices=["assess"])
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.fixture.stat().st_size > 1024 * 1024:
            raise InputError("Maximum input file size is 1 MiB")
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        print(json.dumps(assess(payload), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(f"Invalid assessment request: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
