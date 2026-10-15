"""Opt-in literature search and read-only fusion with the complete Math-MCTS corpus.

Remote responses are research leads, not independently checked mathematics.
This module never downloads a bulk corpus, grants copyright permissions,
promotes source records to trusted rules, or changes the curated manifest.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .fast_index import terms_for
from .source_expansion import import_jsonl

THEOREMSEARCH_API = "https://api.theoremsearch.com/graph/embedding"
THEOREMSEARCH_CREDIT = "https://github.com/uw-math-ai/TheoremSearch"
MAX_RESPONSE_BYTES = 2_000_000
_SUPPORTED = {"theorem", "lemma", "definition", "method", "conjecture", "counterexample"}
_KIND_MAP = {"proposition": "theorem", "corollary": "theorem"}


def _https_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password


def normalize_theoremsearch(data: dict) -> tuple[list[dict], dict]:
    """Conservatively translate documented /graph/embedding results.

    The source_ref denotes a *local content snapshot*, not an immutable upstream
    version or the legal right to redistribute the underlying paper.
    """
    hits = data.get("results") if isinstance(data, dict) else None
    if not isinstance(hits, list):
        raise ValueError("Expected TheoremSearch graph/embedding results array")
    candidates = []
    rejected = {}
    for hit in hits:
        if not isinstance(hit, dict):
            reason = "invalid_hit"
        else:
            body = hit.get("body")
            ident = hit.get("statement_id")
            link = hit.get("url")
            raw_kind = str(hit.get("kind") or "theorem").lower()
            kind = _KIND_MAP.get(raw_kind, raw_kind)
            if not isinstance(body, str) or not 8 <= len(body) <= 12000:
                reason = "missing_or_oversized_statement"
            elif not isinstance(ident, str) or not ident.strip():
                reason = "missing_statement_id"
            elif not _https_url(link):
                reason = "missing_https_primary_source"
            elif kind not in _SUPPORTED:
                reason = "unsupported_kind"
            else:
                reason = ""
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        origin = str(hit.get("source") or "source_unidentified")[:100]
        title = str(hit.get("title") or "Unknown paper")[:900]
        authors = hit.get("authors")
        author_text = "; ".join(str(x) for x in authors)[:950] if isinstance(authors, list) else ""
        name = str(hit.get("name") or ident)[:900]
        token = json.dumps([ident, link, body], ensure_ascii=False, separators=(",", ":"))
        snapshot = hashlib.sha256(token.encode("utf-8")).hexdigest()
        record = {
            "source": origin,
            "source_ref": "api-content-sha256-" + snapshot,
            "source_url": link,
            "license": "unverified; original source permissions apply",
            "locator": "theoremsearch/statement/" + ident[:900],
            "name": name,
            "kind": kind,
            "statement": body,
            "source_provider": "TheoremSearch",
            "provider_url": THEOREMSEARCH_CREDIT,
            "paper_title": title,
            "authors": author_text,
            "original_source": origin,
            "original_kind": raw_kind[:100],
            "external_id": str(hit.get("external_id") or "")[:900],
            "source_precision": "API statement_id and primary paper URL; exact paper section not checked",
            "reuse_policy": "local research cache only; redistribution not authorized by this record",
        }
        candidates.append(record)
    return candidates, {"remote_hits": len(hits), "accepted": len(candidates),
                        "rejected": rejected, "proofs_verified": 0,
                        "source_licenses_verified": 0}


def query_theoremsearch(query: str, *, limit: int = 8, timeout: float = 12.0,
                        opener=None) -> tuple[list[dict], dict]:
    """Explicit, bounded live remote request; never called by MCTS per-node."""
    if not isinstance(query, str) or not query.strip() or len(query) > 3000:
        raise ValueError("Provide a nonempty research question up to 3000 characters")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if not 0 < timeout <= 60:
        raise ValueError("timeout must be between 0 and 60 seconds")
    url = THEOREMSEARCH_API + "?" + urlencode({"query": query, "n_results": limit})
    request = Request(url, headers={"Accept": "application/json",
                                   "User-Agent": "math-mcts-literature-bridge/1"})
    transport = opener or urlopen
    with transport(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Remote theorem response exceeds size limit")
    data = json.loads(raw.decode("utf-8"))
    return normalize_theoremsearch(data)


def cache_theoremsearch(db_path: str | Path, query: str, *, limit: int = 8,
                        opener=None) -> dict:
    """Import unverified literature leads into a local, ignored SQLite cache."""
    rows, report = query_theoremsearch(query, limit=limit, opener=opener)
    if not rows:
        return {**report, "imported": 0, "cache": str(db_path)}
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="math-mcts-literature-") as tmp:
        manifest = Path(tmp) / "leads.jsonl"
        with manifest.open("w", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        result = import_jsonl(path, manifest, max_records=limit)
    return {**report, "imported": result["inserted"],
            "already_present": result["already_present_identical"],
            "cache": str(path), "status": "unreviewed_literature_leads_only"}


class HybridCorpus:
    """Read-only bounded two-index fusion; primary full-index remains mandatory.

    External records are drawn only when explicitly selected via an external DB.
    Their count never enters the primary index's complete-coverage certificate.
    No external MCTS selection is a proof or a semantic applicability check.
    """

    def __init__(self, primary, external_db_path: str | Path, *, quota: int = 6):
        if type(quota) is not int or not 1 <= quota <= 50:
            raise ValueError("external quota must be 1..50")
        self.primary = primary
        self.path = Path(external_db_path)
        if not self.path.is_file():
            raise ValueError("External literature cache does not exist: " + str(self.path))
        self.external = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            self.external.execute("BEGIN")
            self.external_count = self.external.execute(
                "SELECT COUNT(*) FROM external_candidates").fetchone()[0]
            fts_count = self.external.execute(
                "SELECT COUNT(*) FROM external_terms").fetchone()[0]
            if fts_count != self.external_count:
                raise ValueError("External candidate FTS index inconsistent")
            self.source_counts = dict(self.external.execute(
                "SELECT source,COUNT(*) FROM external_candidates GROUP BY source"))
        except (sqlite3.DatabaseError, ValueError):
            self.external.close()
            raise ValueError("Invalid or incomplete external literature cache")
        self.quota = quota
        self._cache = OrderedDict()
        self._qcache = OrderedDict()
        self.external_loaded_ids = set()
        self.external_retrieved_ids = set()
        self.external_search_calls = 0

    def __getattr__(self, key):
        return getattr(self.primary, key)

    def close(self):
        self.external.close()
        self.primary.close()

    def _card(self, row: dict) -> dict:
        cid = row["id"]
        if cid in self._cache:
            self._cache.move_to_end(cid)
            return self._cache[cid]
        statement = row["statement"]
        authors = row.get("authors", "")
        card = {
            "id": cid, "name": row["name"], "english_name": row["name"],
            "domain": row.get("domain") or "unclassified_external",
            "module": row["locator"], "statement": statement,
            "statement_sha256": row["statement_sha256"],
            "source_tier": "unreviewed_external_source",
            "difficulty_level": None, "verification_status": "pending",
            "curation_status": "unreviewed_external_source",
            "source_kind": row["kind"],
            "proof_verified_by_this_search": False,
            "attribution": {
                "source_project": row["source"], "source_project_url": row["source_url"],
                "source_commit": None, "source_snapshot": row["source_ref"],
                "source_locator": row["locator"], "source_provider": row.get("source_provider"),
                "provider_url": row.get("provider_url"),
                "paper_title": row.get("paper_title"), "authors": authors,
                "original_source": row.get("original_source", row["source"]),
                "external_id": row.get("external_id"),
                "doi": row.get("doi"),
                "original_kind": row.get("original_kind", row["kind"]),
                "license": row["license"], "license_verified": False,
                "source_precision": row.get("source_precision"),
                "reuse_policy": row.get("reuse_policy"),
                "mathematics_originality_claim": False,
            },
        }
        card["_tokens"] = frozenset(terms_for(" ".join([
            row["name"], statement, row.get("assumptions", ""),
            row.get("conclusion", ""), row.get("domain", ""),
            row.get("paper_title", ""), row.get("original_source", "")])))
        self.external_loaded_ids.add(cid)
        self._cache[cid] = card
        if len(self._cache) > 512:
            self._cache.popitem(last=False)
        return card

    def get(self, cid):
        if not cid.startswith("EXT_"):
            return self.primary.get(cid)
        if cid in self._cache:
            self._cache.move_to_end(cid)
            return self._cache[cid]
        result = self.external.execute(
            "SELECT record FROM external_candidates WHERE id=?", (cid,)).fetchone()
        if result is None:
            raise KeyError(cid)
        return self._card(json.loads(result[0]))

    def public_card(self, cid):
        return {k: v for k, v in self.get(cid).items() if not k.startswith("_")}

    def search(self, query, limit):
        # Retrieval quota never removes all primary hits, even at limit=1.
        self.external_search_calls += 1
        # Unclassified external results must not bypass an explicit domain filter.
        if getattr(self.primary, 'domain', None) is not None:
            return self.primary.search(query, limit)
        external_limit = min(self.quota, max(0, limit - 1))
        if self.external_count == 0 or external_limit == 0:
            return self.primary.search(query, limit)
        terms = [x for x in terms_for(query)[:24] if x]
        if not terms:
            return self.primary.search(query, limit)
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        key = (expression, external_limit)
        if key in self._qcache:
            ids = self._qcache[key]
            self._qcache.move_to_end(key)
        else:
            # Retrieve a bounded ID-only shortlist, not full text blobs.
            # Balance providers so one huge dataset cannot eclipse the rest.
            shortlist = self.external.execute(
                "SELECT e.id,e.source,e.normalized_statement_sha256 "
                "FROM external_terms t JOIN external_candidates e ON e.rowid=t.rowid "
                "WHERE external_terms MATCH ? "
                "ORDER BY bm25(external_terms),e.id LIMIT ?",
                (expression, min(200, max(external_limit * 16, 32)))).fetchall()
            groups = {}
            seen_hashes = set()
            for cid, source, digest in shortlist:
                if digest in seen_hashes:
                    continue  # lexical duplicate; never claim semantic equivalence
                seen_hashes.add(digest)
                groups.setdefault(source, []).append(cid)
            ids = []
            # Source buckets keep original BM25 order within each provider.
            while len(ids) < external_limit and any(groups.values()):
                for group in groups.values():
                    if group and len(ids) < external_limit:
                        ids.append(group.pop(0))
            self._qcache[key] = ids
            if len(self._qcache) > 128:
                self._qcache.popitem(last=False)
        found = [self.get(cid) for cid in ids]
        self.external_retrieved_ids.update(ids)
        # Reserve only slots actually filled by external hits.
        primary_hits = self.primary.search(query, limit - len(found))
        return primary_hits + found

    def sample(self, rng, limit):
        # Preserve primary global exploration, without falsely sampling every
        # remote theorem ever indexed on the TheoremSearch service.
        return self.primary.sample(rng, limit)

