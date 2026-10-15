"""Research using a single prefetch phase, then fast *offline* MCTS expansions.

All-public queries are explicit. Gated or bulk data require user-acquired files.
No provider is retried implicitly; provider failures and counts are reported.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.indexed_mcts import research_with_knowledge
from math_mcts.source_adapters import discover_candidates, persist_candidates, import_local

DEFAULT_CACHE = Path(".cache/math_mcts/literature.sqlite")
PUBLIC = ("theoremsearch", "s2orc", "zbmath", "realmath")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Source-aware, batched external search + local MCTS")
    parser.add_argument("objective")
    parser.add_argument("--all-public", action="store_true",
                        help="Explicitly query four public discovery endpoints once before MCTS")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--primary-db", type=Path, default=None)
    parser.add_argument("--mathpile", type=Path, help="Authorized local MathPile JSONL")
    parser.add_argument("--realmath", type=Path, help="Local RealMath JSONL")
    parser.add_argument("--zbmath", type=Path, help="Local zbMATH API JSONL")
    parser.add_argument("--s2orc", type=Path, help="Authorized local S2ORC JSONL")
    parser.add_argument("--ack-license", action="store_true",
                        help="Confirm lawful MathPile/S2ORC source access and underlying rights")
    parser.add_argument("--s2orc-text", action="store_true")
    parser.add_argument("--per-source", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    if not 1 <= args.per_source <= 20:
        parser.error("--per-source must be between 1 and 20")

    tasks = {}
    if args.all_public:
        # A single bounded request per source, in parallel, instead of
        # paid network calls during each expanded MCTS state.
        discovered = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(discover_candidates, source, query=args.objective,
                            limit=args.per_source): source
                for source in PUBLIC
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    discovered[source] = future.result()
                except Exception as exc:
                    tasks[source] = {"status": "failed", "reason": str(exc)}
        # Concurrent remote read, serialized and atomic SQLite commits.
        for source in PUBLIC:
            if source in discovered:
                tasks[source] = persist_candidates(args.cache, source, discovered[source])
    # These imports are intentionally sequential: source_expansion SQLite
    # append-only transactions must not fight one another for the same DB.
    for source, path in (("mathpile", args.mathpile), ("s2orc", args.s2orc),
                         ("realmath", args.realmath), ("zbmath", args.zbmath)):
        if path is not None:
            tasks[source + "_local"] = import_local(
                args.cache, source, path, ack_license=args.ack_license,
                include_text=(source == "s2orc" and args.s2orc_text))

    if not args.cache.is_file():
        raise SystemExit("No external cache exists. Prefetch or import a licensed source first.")

    report = research_with_knowledge(
        args.objective, db_path=args.primary_db, external_db_path=args.cache,
        iterations=args.iterations, depth=args.depth, seed=args.seed)
    report["prefetch"] = tasks
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"full_report": str(args.output), "prefetch": tasks,
                          "coverage": report["coverage"], "usage": report["usage"]},
                         ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
