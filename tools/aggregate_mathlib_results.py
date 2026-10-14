"""Independently reconcile every planned source ID with actual Lean shard results.

A complete *extraction* means all registered theorems have an extracted
record matching exact IDs and SHA256. Being attempted or failing to load does
not count. The aggregate never edits original mathematical content.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.lean_fullscale import verify_manifest
from math_mcts.source_registry import SOURCE_COMMIT


def aggregate(plan: Path, shard_root: Path, *, output: Path,
              exports_output: Path | None = None) -> dict:
    verified=verify_manifest(plan)
    manifest=json.loads((plan/"manifest.json").read_text(encoding="utf-8"))
    expected={}
    for shard in manifest["shards"]:
        body=json.loads((plan/shard["file"]).read_text(encoding="utf-8"))
        for batch in body["batches"]:
            for item in batch["records"]:
                expected[item["source_id"]]=item["source_sha256"]
        for item in body["blocked"]:
            expected[item["source_id"]]=None
    if len(expected)!=verified["accounted"]:
        raise RuntimeError("Aggregation source ID coverage mismatch")
    journal={}
    found={}
    for index in range(manifest["shard_count"]):
        root=shard_root/f"shard-{index:03d}"
        status=root/"status.jsonl"
        success=root/"extracted.jsonl"
        if status.is_file():
            for line in status.read_text(encoding="utf-8").splitlines():
                entry=json.loads(line)
                cid=entry["source_id"]
                if cid not in expected or cid in journal:
                    raise ValueError("Duplicate or unknown shard source ID")
                if entry.get("source_sha256")!=expected[cid]:
                    raise ValueError("Stale source SHA in shard results")
                journal[cid]=entry
        if success.is_file():
            for line in success.read_text(encoding="utf-8").splitlines():
                item=json.loads(line)
                cid=item["source_id"]
                if cid in found or cid not in expected:
                    raise ValueError("Duplicate or unknown Lean extraction")
                if item.get("source_statement_sha256")!=expected[cid] or item.get("mathlib_commit")!=SOURCE_COMMIT:
                    raise ValueError("Unpinned Lean extraction")
                found[cid]=item
    for cid,item in found.items():
        if journal.get(cid,{}).get("status")!="extracted":
            raise ValueError("Extracted item not backed by terminal journal")
    for cid,item in journal.items():
        if item["status"]=="extracted" and cid not in found:
            raise ValueError("Missing Lean payload for reported successful extraction")
    status=Counter(item["status"] for item in journal.values())
    unprocessed=len(expected)-len(journal)
    complete=(unprocessed==0 and len(found)==len(expected))
    result={"registered":len(expected),"terminal":len(journal),
            "extracted":len(found),"not_extracted":len(expected)-len(found),
            "not_attempted":unprocessed,
            "blocked_or_failed":len(journal)-len(found),
            "status_counts":dict(sorted(status.items())),
            "mathlib_commit":SOURCE_COMMIT,
            "all_registered_extracted":complete,
            "science_status":"Lean_expression_extracted_not_mathematical_inference_certified",
            "note":"No missing/failed/blocked entries were counted as successful."}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if exports_output is not None:
        exports_output.parent.mkdir(parents=True,exist_ok=True)
        with exports_output.open("w",encoding="utf-8") as out:
            for cid in sorted(found):
                out.write(json.dumps(found[cid],sort_keys=True,ensure_ascii=False)+"\n")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--shard-root",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("lean_full_coverage_report.json"))
    p.add_argument("--exports-output",type=Path,default=Path("all_lean_extracted.jsonl"))
    a=p.parse_args()
    print(json.dumps(aggregate(a.plan,a.shard_root,output=a.output,
                               exports_output=a.exports_output),ensure_ascii=False))
