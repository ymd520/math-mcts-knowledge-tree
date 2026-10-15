"""Opt-in remote theorem discovery, then offline Math-MCTS searching.

Remote content is written only to a local SQLite cache (normally .cache/),
not to tracked knowledge files. No theorem is promoted to the verified catalog.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.literature_bridge import cache_theoremsearch


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cache attributed, unverified literature leads")
    parser.add_argument("query", help="Mathematical search question")
    parser.add_argument("--db", type=Path,
                        default=Path(".cache/math_mcts/literature.sqlite"),
                        help="Local ignored cache; do not commit API response text")
    parser.add_argument("--limit", type=int, default=8, help="Remote result cap: 1..20")
    args = parser.parse_args(argv)
    result = cache_theoremsearch(args.db, args.query, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
