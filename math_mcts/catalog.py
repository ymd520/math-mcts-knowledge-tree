"""Auditable supplemental knowledge packs, overlays and inventory statistics.

Editorial importance is separate from difficulty and formal proof status.
No text card is automatically promoted to a reasoning RuleBook.
"""
from __future__ import annotations
import hashlib
import gzip
import json
import unicodedata
from collections import Counter
from pathlib import Path

PACK_DIR = Path(__file__).with_name("data") / "curated"


def name_key(value):
    return "".join(unicodedata.normalize("NFKC", value).lower().split())


def assemble(base_rows, directory=PACK_DIR):
    directory = Path(directory)
    if not (directory / "manifest.json").exists():
        return list(base_rows), {}
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    rows = {row["id"]: dict(row) for row in base_rows}
    if len(rows) != len(base_rows):
        raise ValueError("Duplicate ID in base catalog")
    order = list(rows)
    added = enriched = 0
    for entry in manifest["packs"]:
        path = directory / entry["file"]
        if path.resolve().parent != directory.resolve():
            raise ValueError("Pack path escapes catalog directory")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("Catalog pack hash mismatch")
        pack = json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)
        if len(pack["concepts"]) != entry["count"]:
            raise ValueError("Catalog pack count mismatch")
        for row in pack["concepts"]:
            if row["id"] in rows:
                raise ValueError("Duplicate catalog ID")
            rows[row["id"]] = row
            order.append(row["id"])
            added += 1
        for patch in pack.get("overlays", []):
            cid = patch["id"]
            if cid not in rows:
                raise ValueError("Overlay references missing concept")
            old = rows[cid]
            digest = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if digest != patch["base_sha256"]:
                raise ValueError(f"Stale editorial overlay: {cid}")
            changes = patch["changes"]
            if "id" in changes:
                raise ValueError("Overlay cannot rename IDs")
            rows[cid] = {**old, **changes}
            enriched += 1
    return [rows[cid] for cid in order], {"catalog_added": added, "catalog_enriched": enriched,
                                          "catalog_version": manifest["version"]}


def inventory(concepts):
    levels = Counter(c.level for c in concepts)
    important = Counter(c.level for c in concepts if {"核心", "重要"} & set(c.tags))
    domains = Counter(c.domain_cn for c in concepts)
    statuses = Counter(c.verification_status or "unspecified" for c in concepts)
    groups = {}
    for c in concepts:
        groups.setdefault(name_key(c.cn), []).append(c.id)
    return {"total": len(concepts), "levels": dict(sorted(levels.items())),
            "important_levels": dict(sorted(important.items())), "domains": dict(domains),
            "verification_statuses": dict(statuses),
            "duplicate_name_groups": sum(len(ids) > 1 for ids in groups.values())}
