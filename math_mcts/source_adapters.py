"""Six-source mathematics adapter layer (metadata and untrusted candidate statements).

Data is always credited, identity-pinned to its content, never promoted to
proof status or silently redistributed. External bulk files must be obtained
and licensed by the user; this module does not bypass gated datasets.
All sources emit the existing source_expansion JSONL schema.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .literature_bridge import cache_theoremsearch
from .source_expansion import import_jsonl

PROJECTS = {
    "theoremsearch": {
        "project": "TheoremSearch", "url": "https://github.com/uw-math-ai/TheoremSearch",
        "data": "https://www.theoremsearch.com/docs", "mode": "remote-live", "license": "per-original-paper"},
    "zbmath": {
        "project": "zbMATH Open KG", "url": "https://github.com/zbMATHOpen/zbmath-open-kg",
        "data": "https://doi.org/10.5281/zenodo.21497975", "mode": "remote-sample-or-local-export",
        "license": "CC BY-SA 4.0 (zbMATH generated content); third-party text restricted"},
    "s2orc": {
        "project": "S2ORC", "url": "https://github.com/allenai/s2orc",
        "data": "https://api.semanticscholar.org/api-docs/datasets",
        "mode": "public-paper-search-or-authorized-local-bulk",
        "license": "ODC-By 1.0 database; paper content may carry additional rights"},
    "realmath": {
        "project": "RealMath", "url": "https://github.com/ethz-spylab/RealMath",
        "data": "https://huggingface.co/datasets/ethz-spylab/RealMath",
        "mode": "public-dataset-viewer-or-local-export", "license": "check actual dataset and original papers"},
    "mathpile": {
        "project": "MathPile", "url": "https://github.com/GAIR-NLP/MathPile",
        "data": "https://huggingface.co/datasets/GAIR/MathPile",
        "mode": "user-authorized-gated-local-export",
        "license": "CC BY-NC-SA 4.0 or stricter original terms"},
    "mathlib4": {
        "project": "mathlib4", "url": "https://github.com/leanprover-community/mathlib4",
        "data": "https://github.com/leanprover-community/mathlib4",
        "mode": "existing-pinned-local-index", "license": "Apache-2.0"},
}
ZBMATH_PIN = "f304ad24ae568827ff0a310b86e0e874dc71a12f"
ZBMATH_SAMPLE = ("https://raw.githubusercontent.com/zbMATHOpen/zbmath-open-kg/"
                 + ZBMATH_PIN + "/data/sample.jsonl")
S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
REALMATH_HF = "https://datasets-server.huggingface.co"
MAX_BODY = 4_000_000
MAX_ROW = 12000


def _first(x, default=""):
    if isinstance(x, list):
        return next((str(v) for v in x if v is not None and str(v).strip()), default)
    return str(x) if x is not None else default


def _authors(x):
    if isinstance(x, list):
        return "; ".join(_first(a.get("name")) if isinstance(a, dict) else str(a)
                         for a in x if a is not None)[:950]
    return _first(x)[:950]


def _url(x, fallback):
    x = _first(x)
    if x.startswith("http://arxiv.org/"):
        x = "https://" + x[len("http://"):]
    p = urlparse(x)
    return x if p.scheme == "https" and p.hostname and not p.username and not p.password else fallback


def _compact(v, maxlen=900):
    return str(v or "").strip()[:maxlen]


def _record(source, rid, title, statement, kind, source_url, *,
            license, authors="", doi="", domain="", locator="", source_precision="",
            external_id="", provider_url="", reuse_policy="cache-only; never redistribute until rights reviewed",
            index=0, source_ref=None):
    statement = _compact(statement, MAX_ROW)
    if len(statement) < 8:
        return None
    seed = json.dumps([source, rid, statement], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "source": source, "source_ref": source_ref or "record-sha256-" + digest,
        "source_url": _url(source_url, PROJECTS[source]["data"]),
        "license": _compact(license), "locator": _compact(locator or (str(rid) + ":" + str(index))),
        "name": _compact(title), "kind": kind, "statement": statement,
        "paper_title": _compact(title), "authors": _compact(authors),
        "external_id": _compact(external_id or rid), "doi": _compact(doi),
        "domain": _compact(domain), "source_provider": PROJECTS[source]["project"],
        "provider_url": provider_url or PROJECTS[source]["url"],
        "source_precision": source_precision or "dataset_metadata_not_exact_statement_line",
        "reuse_policy": reuse_policy,
    }


def normalize_zbmath(row, index=0):
    """zbMATH OA API / KG JSONL record; reviews are reviews, never theorems."""
    rid = _first(row.get("zbl_id")) or _first(row.get("document_id"))
    title = _first(row.get("document_title"))
    if not rid or not title:
        return None
    doi = _first(row.get("doi"))
    keywords = row.get("keyword", [])
    msc = row.get("classification", [])
    review = _first(row.get("review_text"))
    note = "Title: " + title
    if keywords:
        note += "; Keywords: " + ", ".join(str(x) for x in keywords if x)[:2000]
    if msc:
        note += "; MSC: " + ", ".join(str(x) for x in msc if x)[:600]
    # Reviews are included only in the credited local evidence cache.
    if review and "contents unavailable due to conflicting licenses" not in review.lower():
        note += "; zbMATH reviewer summary: " + review[:6000]
    return _record("zbmath", rid, title, note, "review",
                   "https://zbmath.org/" + rid, license=PROJECTS["zbmath"]["license"],
                   authors=_authors(row.get("author", [])), doi=doi,
                   domain=", ".join(str(x) for x in msc if x)[:900],
                   source_precision="zbMATH publication/review metadata; not a proved theorem")


def normalize_semantic_scholar(row, index=0):
    """Public S2AG paper metadata discovery, NOT S2ORC full text."""
    rid = _first(row.get("paperId")) or _first(row.get("corpusId"))
    title = _first(row.get("title"))
    if not rid or not title:
        return None
    ids = row.get("externalIds") or {}
    arxiv = _first(ids.get("ArXiv"))
    url = ("https://arxiv.org/abs/" + arxiv) if arxiv else row.get("url")
    doi = _first(ids.get("DOI"))
    year = _first(row.get("year"))
    fields = row.get("fieldsOfStudy") or []
    statement = "Paper title: " + title + ("; Publication year: " + year if year else "")
    if fields:
        statement += "; Fields: " + ", ".join(str(x) for x in fields)
    return _record("s2orc", rid, title, statement, "paper", url,
                   license="paper bibliographic metadata; source full-text rights unverified",
                   authors=_authors(row.get("authors")), doi=doi,
                   source_precision="Semantic Scholar graph metadata only; not S2ORC parsed text")


def normalize_s2orc(row, index=0, *, include_text=False):
    """S2ORC datasets/v1 parsed-text record, obtained through authorized bulk API."""
    content = row.get("content") or {}
    if not isinstance(content, dict):
        content = {}
    ids = row.get("externalids") or row.get("externalIds") or {}
    rid = _first(row.get("corpusid")) or _first(row.get("corpusId"))
    title = _first(row.get("title")) or "S2ORC research paper " + rid
    if not rid:
        return None
    arxiv = _first(ids.get("ArXiv"))
    doi = _first(ids.get("DOI"))
    src = content.get("source") or {}
    pdfs = src.get("pdfurls", []) if isinstance(src, dict) else []
    url = "https://arxiv.org/abs/" + arxiv if arxiv else (pdfs[0] if pdfs else "")
    body = content.get("text") if include_text else None
    text = _compact(body, MAX_ROW) if isinstance(body, str) else "Paper metadata: " + title
    return _record("s2orc", rid, title, text, "excerpt" if include_text else "paper", url,
                   license=PROJECTS["s2orc"]["license"], doi=doi,
                   source_precision="S2ORC parsed paper text excerpt" if include_text else "S2ORC metadata-only",
                   reuse_policy="local cache only; underlying paper redistribution not authorized")


def normalize_realmath(row, index=0):
    link = _first(row.get("link"))
    theorem = _first(row.get("theorem"))
    if not link or not theorem:
        return None
    title = _first(row.get("question"))[:150] or ("RealMath theorem " + str(index))
    rid = link.rstrip("/") + "/" + str(index)
    return _record("realmath", rid, title, theorem, "theorem", link,
                   license="dataset/original paper terms not verified",
                   authors="not supplied by dataset row",
                   source_precision="extracted theorem in RealMath benchmark, exact paper position unknown",
                   reuse_policy="local research only; no proof-verification claim or redistribution")


def normalize_mathpile(row, index=0):
    text = _first(row.get("text"))
    if not text:
        return None
    meta = row.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    subset = _first(row.get("SubSet")) or _first(row.get("subset")) or "unknown"
    orig = _first(meta.get("url")) or _first(meta.get("source_url"))
    # Preserve transparency if an original source URL is missing.
    rid = _first(meta.get("idx")) or str(index)
    title = "MathPile / " + subset + " / " + rid
    return _record("mathpile", subset + "/" + rid, title, text, "excerpt",
                   orig or PROJECTS["mathpile"]["data"],
                   license=PROJECTS["mathpile"]["license"],
                   authors=_first(meta.get("authors")) or "unknown original authors",
                   source_precision=("source URL supplied by dataset row" if orig else
                                     "only MathPile subset/index known; original text source unknown"),
                   reuse_policy="requires prior user access acceptance; local non-commercial cache only; "
                                "original source restrictions may be stricter")


NORMALIZERS = {
    "zbmath": normalize_zbmath, "s2orc": normalize_s2orc,
    "s2orc-search": normalize_semantic_scholar,
    "realmath": normalize_realmath, "mathpile": normalize_mathpile,
}


def _fetch_json(url, *, opener=None, timeout=15):
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise ValueError("HTTPS required for network source")
    transport = opener or urlopen
    request = Request(url, headers={"User-Agent": "math-mcts-metadata-bridge/1",
                                   "Accept": "application/json"})
    with transport(request, timeout=timeout) as response:
        b = response.read(MAX_BODY + 1)
    if len(b) > MAX_BODY:
        raise ValueError("Source response exceeds network limit")
    return json.loads(b)


def fetch_s2orc_papers(query, *, limit=10, opener=None):
    """Public Semantic Scholar paper DISCOVERY, not parsed full-text retrieval."""
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("Invalid paper search query")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    url = S2_SEARCH + "?" + urlencode({"query": query, "limit": limit,
                        "fields": "paperId,title,authors,year,url,externalIds,fieldsOfStudy"})
    data = _fetch_json(url, opener=opener)
    rows = data.get("data", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid Semantic Scholar response")
    return [r for i, item in enumerate(rows[:limit])
            if (r := normalize_semantic_scholar(item, i)) is not None]


def fetch_realmath_rows(*, limit=25, split="Math_arXiv", opener=None):
    """Hugging Face public dataset viewer: discover actual split/config first."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    splits = _fetch_json(REALMATH_HF + "/splits?" +
                         urlencode({"dataset": "ethz-spylab/RealMath"}), opener=opener)
    candidates = splits.get("splits") or []
    chosen = next((x for x in candidates if x.get("split") == split), None)
    if not chosen:
        raise ValueError("RealMath dataset split unavailable: " + split)
    url = REALMATH_HF + "/rows?" + urlencode({
        "dataset": "ethz-spylab/RealMath", "config": chosen["config"],
        "split": chosen["split"], "offset": 0, "length": limit})
    data = _fetch_json(url, opener=opener)
    rows = data.get("rows") or []
    return [record for i, row in enumerate(rows)
            if isinstance(row, dict)
            and (record := normalize_realmath(row.get("row") or {}, row.get("row_idx", i))) is not None]


def fetch_zbmath_sample(*, opener=None):
    """Fetch an upstream pinned public JSONL sample of zbMATH generated metadata."""
    p = urlparse(ZBMATH_SAMPLE)
    req = Request(ZBMATH_SAMPLE, headers={"User-Agent": "math-mcts-zbmath-sample/1"})
    with (opener or urlopen)(req, timeout=15) as resp:
        raw = resp.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise ValueError("zbMATH sample exceeds request limit")
    rows = []
    for i, line in enumerate(raw.decode("utf-8").splitlines()):
        if line.strip():
            item = normalize_zbmath(json.loads(line), i)
            if item is not None:
                rows.append(item)
    return rows


def _open_jsonl(path: Path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _write_candidates(db, items, *, max_records=1000):
    """Small bounded staging batch; SQLite import is atomic and idempotent."""
    import tempfile
    if not items:
        return {"input_records": 0, "inserted": 0, "already_present_identical": 0}
    with tempfile.TemporaryDirectory(prefix="math-mcts-source-") as tmp:
        path = Path(tmp) / "records.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in items:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return import_jsonl(db, path, max_records=max_records)


def import_local(db, source, path, *, max_records=10000, ack_license=False,
                 include_text=False, batch_size=500):
    """Stream source-native local JSONL / .jsonl.gz without storing inputs in Git.

    MathPile is gated/non-commercial; explicit acceptance needed. S2ORC parsed
    text also requires explicit acknowledgement of applicable paper licenses.
    """
    if source not in {"zbmath", "realmath", "s2orc", "mathpile"}:
        raise ValueError("Use zbmath, realmath, s2orc, or mathpile local adapter")
    if source == "mathpile" and not ack_license:
        raise PermissionError("MathPile gated dataset and underlying source terms require --ack-license")
    if source == "s2orc" and include_text and not ack_license:
        raise PermissionError("S2ORC parsed text requires --ack-license for underlying paper rights")
    if max_records < 1 or batch_size < 1:
        raise ValueError("Positive max_records and batch_size required")
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    normalize = NORMALIZERS[source]
    total = 0
    inserted = 0
    skipped = 0
    batch = []
    for i, raw in enumerate(_open_jsonl(path)):
        if total >= max_records:
            break
        total += 1
        item = normalize(raw, i, include_text=include_text) if source == "s2orc" else normalize(raw, i)
        if not item:
            skipped += 1
            continue
        batch.append(item)
        if len(batch) >= batch_size:
            imported = _write_candidates(db, batch, max_records=batch_size)
            inserted += imported["inserted"]
            batch.clear()
    if batch:
        inserted += _write_candidates(db, batch, max_records=batch_size)["inserted"]
    return {"source": source, "scanned": total, "inserted": inserted,
            "skipped": skipped, "status": "unreviewed_evidence_cache_only",
            "full_dataset_indexed": False, "proofs_verified": 0,
            "license_acceptance_declared": bool(ack_license)}


def discover_candidates(source, *, query="", limit=10, opener=None):
    """Pure bounded network discovery; does not touch a local SQLite database."""
    if source == "theoremsearch":
        from .literature_bridge import query_theoremsearch
        rows, stats = query_theoremsearch(query, limit=limit, opener=opener)
        return rows
    if source == "s2orc":
        return fetch_s2orc_papers(query, limit=limit, opener=opener)
    if source == "realmath":
        return fetch_realmath_rows(limit=limit, opener=opener)
    if source == "zbmath":
        return fetch_zbmath_sample(opener=opener)[:limit]
    raise ValueError("Only documented public discovery interfaces support live fetch")


def persist_candidates(db, source, rows):
    """Serial cache writer. Safe to call after concurrent network prefetch."""
    report = _write_candidates(db, rows, max_records=max(1, len(rows)))
    return {"source": source, "network_results": len(rows),
            "inserted": report["inserted"],
            "status": "external_unreviewed_candidates_only"}


def fetch_into_cache(db, source, *, query="", limit=10, opener=None):
    """Explicit live discovery, followed by local unreviewed staging."""
    if source == "theoremsearch":
        return cache_theoremsearch(db, query, limit=limit, opener=opener)
    rows = discover_candidates(source, query=query, limit=limit, opener=opener)
    return persist_candidates(db, source, rows)
