"""Reproducible generic knowledge-MCTS case study, not a mathematical prover.

Run both an original full-corpus control and an opt-in mixed source trial.
Any external network source failure is explicit; empty caches are not silently
credited as new mathematical knowledge. Keeps all full traces as CI artifacts.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.indexed_mcts import research_with_knowledge
from math_mcts.source_adapters import discover_candidates, persist_candidates

PUBLIC = ("theoremsearch", "s2orc", "zbmath", "realmath")


def head_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def preview(report):
    ids = {x for p in report["paths"] for x in p["knowledge_ids"]}
    cards = [c for c in report["knowledge_records"] if c["id"] in ids]
    # The order is a citation lead list, not a proof chain.
    cards.sort(key=lambda c: (c["id"] not in ids, c["id"]))
    snippets = []
    for c in cards[:18]:
        attribution = c.get("attribution") or {}
        snippets.append({
            "id": c["id"], "name": c["name"], "source_tier": c["source_tier"],
            "kind": c.get("source_kind"), "source": attribution.get("source_project"),
            "author": attribution.get("authors") or attribution.get("original_theorem_author"),
            "url": attribution.get("source_project_url") or attribution.get("source_module_url"),
            "module": c.get("module"), "statement": c.get("statement", "")[:220],
            "proof_verified": bool(c.get("proof_verified_by_this_search", False)),
        })
    return {
        "objective": report["objective"], "coverage": report["coverage"],
        "usage": report["usage"], "mcts": report["mcts"],
        "elapsed_seconds": report["elapsed_seconds"],
        "paths": report["paths"][:3], "candidate_citations": snippets,
        "proof_verified": report["proof_verified"],
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--external-db", type=Path,
                   default=Path(".cache/math_mcts/g5c_literature.sqlite"))
    p.add_argument("--prefetch", action="store_true",
                   help="Explicitly query permitted public discovery APIs once")
    p.add_argument("--primary-db", type=Path,
                   default=Path(".cache/math_mcts/full_corpus.sqlite"))
    args = p.parse_args(argv)
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes)
    start = perf_counter()
    prefetch = {}
    if args.prefetch:
        # Network requests in parallel; local SQLite transaction imports serialized.
        query = config["objectives"][0]["query"]
        fetched = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(discover_candidates, source,
                      query=query, limit=config.get("external_prefetch_limit", 6)): source
                      for source in PUBLIC}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    fetched[source] = future.result()
                except Exception as e:
                    prefetch[source] = {"status": "failed", "error": str(e)}
        for source in PUBLIC:
            if source in fetched:
                try:
                    prefetch[source] = persist_candidates(args.external_db, source,
                                                          fetched[source])
                except Exception as e:
                    prefetch[source] = {"status": "cache_error", "error": str(e)}
    runs = {}
    objective = config["objectives"][0]["query"]
    # Control and trial share seed, budget and primary source inventory.
    plan = [("control_full_index", objective, False,
             config["objectives"][0]["iterations"])]
    plan += [("hybrid_" + o["label"], o["query"], True, o["iterations"])
             for o in config["objectives"]]
    for label, query, wants_external, iterations in plan:
        mixed = wants_external and args.external_db.is_file()
        raw = research_with_knowledge(
            query, db_path=args.primary_db if args.primary_db.is_file() else None,
            external_db_path=args.external_db if mixed else None,
            iterations=iterations, depth=config["depth"],
            retrieval_width=config["retrieval_width"],
            exploration_width=config["exploration_width"],
            seed=config["seed"], top_k=5)
        runs[label] = raw
        digest = {
            "label": label, "actual_depth": raw["usage"]["actual_tree_depth"],
            "selected": raw["usage"]["distinct_cards_selected_in_tree"],
            "selected_by_tier": raw["usage"]["selected_by_source_tier"],
            "external_cache_enabled": raw["coverage"]["external_cache_enabled"],
            "external_candidates_by_source": raw["coverage"]["external_candidates_by_source"],
            "full_index": raw["coverage"]["indexed_total"],
            "elapsed_seconds": raw["elapsed_seconds"],
            "proof_verified": raw["proof_verified"],
        }
        print(json.dumps(digest, ensure_ascii=False), flush=True)
    report = {
        "status": "completed_MCTS_retrieval_experiment_not_proof",
        "case_id": config["case_id"], "mathematical_problem": config["mathematical_problem"],
        "git_commit": head_sha(), "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "python": platform.python_version(), "seed": config["seed"],
        "requested_max_depth": config["depth"], "prefetch": prefetch,
        "data_status": {"mathpile_full_dataset": "not_loaded",
                        "s2orc_full_dataset": "not_loaded",
                        "theoremsearch_full_dataset": "not_loaded",
                        "full_mathlib_primary_index": "validated_by_research_with_knowledge"},
        "comparisons": {name: preview(raw) for name, raw in runs.items()},
        "raw_reports": runs,
        "whole_job_elapsed_seconds": perf_counter() - start,
        "interpretation": (
            "This code selects literature/knowledge paths. No candidate is automatically "
            "mathematically applicable, original or proof verified; no G5C resolution."),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("RESEARCH_RESULT_FILE=" + str(args.output), flush=True)
    print("SUMMARY=" + json.dumps({
        "prefetch": prefetch, "comparisons": {k: {
            "coverage": v["coverage"], "usage": v["usage"],
            "paths": v["paths"][:2], "candidate_citations": v["candidate_citations"][:8],
        } for k, v in report["comparisons"].items()}
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
