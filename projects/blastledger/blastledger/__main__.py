"""CLI: python -m blastledger assess fixtures/danger.json"""
import argparse
import json
from pathlib import Path
import sys
from .engine import assess, InputError


def main():
    parser = argparse.ArgumentParser(description="BlastLedger change-risk assessment (read-only)")
    parser.add_argument("command", choices=["assess"])
    parser.add_argument("fixture", type=Path, help="local JSON service manifest and change")
    args = parser.parse_args()
    try:
        if args.fixture.stat().st_size > 2_000_000:
            raise InputError("Input larger than 2MB")
        data = json.loads(args.fixture.read_text(encoding="utf-8"))
        print(json.dumps(assess(data), indent=2, sort_keys=True))
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
