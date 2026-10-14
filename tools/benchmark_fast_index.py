"""Measure query latency of the FTS index without unsupported speedup claims."""
from __future__ import annotations
import argparse
import json
import sqlite3
import statistics
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.fast_index import fast_search, index_stats


def benchmark(db: Path, queries: list[str], repetitions: int = 5) -> dict:
    samples = []
    checks = []
    for query in queries:
        durations = []
        found = 0
        for _ in range(repetitions):
            t0 = time.perf_counter()
            result = fast_search(db, query, top_k=10)
            durations.append(1000.0 * (time.perf_counter() - t0))
            found = len(result)
        samples.extend(durations)
        checks.append({"query": query, "result_count": found,
                       "median_ms": statistics.median(durations)})
    samples.sort()
    if not samples:
        raise ValueError("No search timings")
    return {
        "index": index_stats(db),
        "queries": checks,
        "total_queries_timed": len(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": samples[min(len(samples) - 1, int(0.95 * (len(samples)-1)))],
        "note": "Hardware-dependent FTS latency, not an apples-to-apples MCTS baseline",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("fts_benchmark.json"))
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--queries", nargs="+", default=[
        "group", "matrix", "integral", "topology", "smul", "convolution",
        "矩阵", "积分", "群", "函数",
    ])
    a = parser.parse_args()
    report = benchmark(a.db, a.queries, a.repetitions)
    a.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"median_ms": report["median_ms"], "p95_ms": report["p95_ms"],
                      "index": report["index"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
