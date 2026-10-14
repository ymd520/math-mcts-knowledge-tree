"""Register imported theorem declarations as auditable, ungraded source records."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.source_registry import register_source_statements, get_registered_statement


def main():
    p = argparse.ArgumentParser(description="Register source-verified statements (no importance promotion)")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--manifest", type=Path, default=Path("official_source_registry.jsonl.gz"))
    p.add_argument("--report", type=Path, default=Path("source_registration_report.json"))
    p.add_argument("--show-id", help="Read a registered theorem declaration by source ID")
    a = p.parse_args()
    if a.show_id:
        print(json.dumps(get_registered_statement(a.db, a.show_id),
                         ensure_ascii=False, indent=2))
        return
    result = register_source_statements(a.db, a.manifest)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
