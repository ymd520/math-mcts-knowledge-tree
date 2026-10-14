"""Build and browse the classified 100k-source mathematical knowledge layer.

From repository root:
  python tools/classify_knowledge.py --db math_index.sqlite --report knowledge_classification.json
  python tools/classify_knowledge.py --db math_index.sqlite --domain 代数 --limit 10
  python tools/classify_knowledge.py --db math_index.sqlite --search convolution
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.knowledge_bank import KnowledgeBank, classify_knowledge


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--report", type=Path, default=Path("knowledge_classification.json"))
    p.add_argument("--browse", action="store_true")
    p.add_argument("--domain", help="Normalized domain (e.g., 代数 / 分析)")
    p.add_argument("--kind", help="e.g. 定理声明")
    p.add_argument("--tier", choices=["curated", "unreviewed_import"])
    p.add_argument("--after-id", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--search")
    p.add_argument("--show-id")
    args = p.parse_args()
    if args.search or args.show_id or args.browse:
        bank = KnowledgeBank(args.db)
        if args.show_id:
            result = bank.get(args.show_id)
        elif args.search:
            result = bank.search(args.search, top_k=args.limit, domain=args.domain,
                                 kind=args.kind, source_tier=args.tier)
        else:
            result = bank.browse(domain=args.domain, kind=args.kind,
                                 source_tier=args.tier, after_id=args.after_id,
                                 limit=args.limit)
    else:
        result = classify_knowledge(args.db)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                               + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
