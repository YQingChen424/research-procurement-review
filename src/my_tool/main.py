"""Command line entry point: python -m my_tool.main review ..."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from my_tool.core.review import review_batch
from my_tool.utils.files import load_config, load_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only research procurement review prototype")
    parser.add_argument("review", choices=["review"])
    parser.add_argument("--input", type=Path, required=True, help="JSON file with catalog and requests")
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--output", type=Path, help="Write JSON result to this path")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    config = load_config(args.config)
    result = review_batch(
        load_json(args.input),
        as_of=args.as_of,
        max_catalog_age_days=int(config["max_catalog_age_days"]),
    )
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
