"""Export a review-only queue from the scalable source search index.

The queue is data-backed, not fabricated mathematical knowledge: source IDs,
formal statements and provenance are retained verbatim. Proposed school levels
and importance remain blank until independently assigned and accepted.
"""
from __future__ import annotations
import argparse
import gzip
import json
import sqlite3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.knowledge import KnowledgeTree
from math_mcts.scale_plan import write_status


def export_queue(db: Path, output: Path, summary: Path):
    with sqlite3.connect(str(db)) as conn, gzip.open(output, "wt", encoding="utf-8") as f:
        rows = conn.execute("SELECT record FROM documents "
                            "WHERE tier='unreviewed_import' ORDER BY domain, id")
        count = 0
        for (blob,) in rows:
            record = json.loads(blob)
            item = {
                "source_concept_id": record["id"],
                "statement_name": record.get("en", ""),
                "statement": record.get("formal", "") or record.get("definition", ""),
                "source_module": record.get("module", ""),
                "source_url": record.get("source_url", "") or record.get("doc_url", ""),
                "source_statement_sha256": record.get("original_metadata", {}).get("陈述SHA256", ""),
                "importance_status": "pending_human_review",
                "actual_level": None,
                "importance_reason": None,
                "reviewer": None,
                "review_evidence": None,
            }
            f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    report = write_status(summary, KnowledgeTree.load(), unreviewed_candidates=count)
    return {"exported": count, "remaining_for_100k_curated_target": report["remaining"],
            "note": "Review queue is not formal important-knowledge catalog"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("source_review_queue.jsonl.gz"))
    p.add_argument("--summary", type=Path, default=Path("scale_status.json"))
    args = p.parse_args()
    print(json.dumps(export_queue(args.db, args.output, args.summary), ensure_ascii=False))


if __name__ == "__main__":
    main()
