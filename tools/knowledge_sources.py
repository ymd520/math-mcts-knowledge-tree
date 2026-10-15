"""Math-MCTS six-source discovery and ingestion CLI.

Usage:
  python tools/knowledge_sources.py status
  python tools/knowledge_sources.py fetch theoremsearch "spectral gaps in finite groups"
  python tools/knowledge_sources.py fetch s2orc "spectral gaps finite groups"
  python tools/knowledge_sources.py fetch zbmath --limit 20
  python tools/knowledge_sources.py fetch realmath --limit 20
  python tools/knowledge_sources.py import mathpile /authorized/data/mathpile.jsonl.gz --ack-license
  python tools/knowledge_sources.py import s2orc /authorized/data/shard.jsonl.gz --include-text --ack-license

No remote service is queried by normal MCTS research: prefetch once, then offline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.source_adapters import PROJECTS, fetch_into_cache, import_local

DEFAULT_DB = Path(".cache/math_mcts/literature.sqlite")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Legal, attributed, opt-in mathematics source adapters")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    fetch = sub.add_parser("fetch", help="Explicit bounded live public discovery")
    fetch.add_argument("source", choices=["theoremsearch", "s2orc", "zbmath", "realmath"])
    fetch.add_argument("query", nargs="?", default="")
    fetch.add_argument("--limit", type=int, default=10)
    fetch.add_argument("--db", type=Path, default=DEFAULT_DB)
    imp = sub.add_parser("import", help="Import a locally authorized source export")
    imp.add_argument("source", choices=["zbmath", "s2orc", "realmath", "mathpile"])
    imp.add_argument("input", type=Path)
    imp.add_argument("--db", type=Path, default=DEFAULT_DB)
    imp.add_argument("--max-records", type=int, default=10000)
    imp.add_argument("--ack-license", action="store_true",
                     help="Confirm source access and all applicable underlying rights")
    imp.add_argument("--include-text", action="store_true", help="S2ORC text; otherwise metadata")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(PROJECTS, ensure_ascii=False, indent=2))
        return
    if args.command == "fetch":
        report = fetch_into_cache(args.db, args.source, query=args.query, limit=args.limit)
    else:
        report = import_local(args.db, args.source, args.input,
                              max_records=args.max_records, ack_license=args.ack_license,
                              include_text=args.include_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
