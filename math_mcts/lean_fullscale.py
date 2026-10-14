"""Exhaustive *planning* and independently auditable shard manifests.

Every source-registered theorem is assigned to one and only one shard. Planning
is not extraction: only a Lean run at the pinned environment can produce
source-aligned evidence. Non-renderable names are not silently discarded.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .source_registry import SOURCE_COMMIT

# Lean Name.str builds names from UTF-8 segments: retain legitimate Unicode
# and quoted-name characters. Only reject controls, invalid dot segmentation
# and pathological lengths; failed environment lookup is a *reported* outcome.
VALID_NAME = re.compile(r"^[^.\\x00-\\x1f\\x7f]+(?:\\.[^.\\x00-\\x1f\\x7f]+)*$")
VALID_MODULE = re.compile(r"^Mathlib(?:\.[A-Za-z_][A-Za-z0-9_']*)+$")
PINNED_TOOLCHAIN = "leanprover/lean4:v4.35.0-rc4"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def plan_full_corpus(db_path: str | Path, output: str | Path, *,
                     shards: int = 64, batch_size: int = 80) -> dict:
    """All registered IDs must be accounted for in executable or blocked bins."""
    if not 1 <= shards <= 256 or not 1 <= batch_size <= 1000:
        raise ValueError("shards must be 1..256, batch_size 1..1000")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict]] = defaultdict(list)
    blocked = []
    seen = set()
    with sqlite3.connect(str(db_path)) as db:
        rows = db.execute("""SELECT sr.id, sr.module, sr.source_sha256,
                                   sr.imported_commit, d.record
              FROM source_registry sr JOIN documents d ON d.id=sr.id
              ORDER BY sr.module, sr.id""")
        for cid, module, digest, commit, raw in rows:
            row = json.loads(raw)
            if cid in seen or row["id"] != cid or commit != SOURCE_COMMIT:
                raise ValueError("Corrupt or stale registered source corpus")
            seen.add(cid)
            if row.get("module") != module or not isinstance(digest,str):
                raise ValueError("Source registry does not match document")
            name = str(row.get("en") or "")
            formal = str(row.get("formal") or "")
            prefix = "theorem " + name
            if not formal.startswith(prefix) or _sha(formal[len(prefix):].strip().encode()) != digest:
                raise ValueError("Registered source statement changed")
            if not VALID_MODULE.fullmatch(module):
                blocked.append({"source_id":cid, "module":module,
                                "reason":"unsupported_module_namespace"})
                continue
            if len(name)>1024 or not VALID_NAME.fullmatch(name):
                blocked.append({"source_id":cid, "module":module,
                                "reason":"unsupported_declaration_identifier"})
                continue
            groups[module].append({"source_id":cid, "name":name, "module":module,
                                   "source_sha256":digest})
        total = db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
    if len(seen) != total:
        raise RuntimeError("Unaccounted source records")
    # Greedy, deterministic module-packing avoids repeating the same Mathlib
    # import across different shards except for oversized modules.
    assignments = [[] for _ in range(shards)]
    loads = [0]*shards
    for module, records in sorted(groups.items(),
                                  key=lambda x:(-len(x[1]),x[0])):
        shard = min(range(shards),key=lambda x:(loads[x],x))
        assignments[shard].append((module,records))
        loads[shard] += len(records)
    blocked_by_shard = [[] for _ in range(shards)]
    for record in blocked:
        ix = int(_sha(record["source_id"].encode())[:8],16) % shards
        blocked_by_shard[ix].append(record)
    results = []
    all_emitted = set()
    for i, assigned in enumerate(assignments):
        batches = []
        for module, records in sorted(assigned):
            for index in range(0,len(records),batch_size):
                block = records[index:index+batch_size]
                for item in block:
                    if item["source_id"] in all_emitted:
                        raise RuntimeError("Duplicate planned theorem")
                    all_emitted.add(item["source_id"])
                batches.append({
                    "module":module, "batch_number":index//batch_size,
                    "records":block,
                })
        piece = {"schema":"1","shard":i,"shard_count":shards,
                 "mathlib_commit":SOURCE_COMMIT,
                 "lean_toolchain":PINNED_TOOLCHAIN,
                 "batches":batches,
                 "blocked":sorted(blocked_by_shard[i],key=lambda x:x["source_id"])}
        body = _canonical(piece)
        filename = f"shard-{i:03d}.json"
        (root/filename).write_bytes(body)
        results.append({"shard":i,"file":filename, "sha256":_sha(body),
                        "candidate_count":sum(len(b["records"]) for b in batches),
                        "blocked_count":len(piece["blocked"]),
                        "modules":len(assigned),"batches":len(batches)})
    if len(all_emitted)+len(blocked) != total:
        raise RuntimeError("Shards do not account for every source record")
    summary = {
        "schema":"1", "mathlib_commit":SOURCE_COMMIT,
        "lean_toolchain":PINNED_TOOLCHAIN,
        "registered_total":total,
        "renderable_total":len(all_emitted),
        "blocked_identifiers_or_modules":len(blocked),
        "shard_count":shards, "batch_size":batch_size,
        "shards":results,
        "plan_is_not_lean_extraction":True,
        "completion_requires_all_source_ids_terminal":True,
    }
    (root/"manifest.json").write_bytes(_canonical(summary))
    return summary


def verify_manifest(root: str | Path, *, expected_total: int | None = None) -> dict:
    root=Path(root)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if manifest["mathlib_commit"] != SOURCE_COMMIT:
        raise ValueError("Stale mathlib commit")
    seen=set()
    blocks=0
    done=0
    for entry in manifest["shards"]:
        path=root/entry["file"]
        content=path.read_bytes()
        if path.resolve().parent != root.resolve() or _sha(content)!=entry["sha256"]:
            raise ValueError("Tampered shard manifest")
        piece=json.loads(content)
        if piece["shard"]!=entry["shard"] or piece["mathlib_commit"]!=SOURCE_COMMIT:
            raise ValueError("Invalid shard identifier/commit")
        candidate_ids=[r["source_id"] for b in piece["batches"] for r in b["records"]]
        blocked_ids=[r["source_id"] for r in piece["blocked"]]
        if len(candidate_ids)!=entry["candidate_count"] or len(blocked_ids)!=entry["blocked_count"]:
            raise ValueError("Shard coverage mismatch")
        for cid in candidate_ids+blocked_ids:
            if cid in seen:
                raise ValueError("Source ID assigned to multiple shards")
            seen.add(cid)
        done+=len(candidate_ids)
        blocks+=len(blocked_ids)
    if done!=manifest["renderable_total"] or blocks!=manifest["blocked_identifiers_or_modules"]:
        raise ValueError("Incomplete shard counts")
    if len(seen)!=manifest["registered_total"]:
        raise ValueError("Registered source loss")
    if expected_total is not None and len(seen)!=expected_total:
        raise ValueError("Unexpected real source corpus total")
    return {"accounted":len(seen),"planned_for_lean":done,
            "blocked_before_lean":blocks,"shards":len(manifest["shards"]),
            "status":"planned_not_extracted"}
