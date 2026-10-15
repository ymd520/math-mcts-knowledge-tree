# Six-source literature adapters for Math-MCTS

## Actual integration routes (not claims that all external corpora were imported)

| Source | Adapter | Access |
| --- | --- | --- |
| [TheoremSearch](https://github.com/uw-math-ai/TheoremSearch) | GET /graph/embedding, attributed candidate import | Explicit network prefetch |
| [zbMATH Open KG](https://github.com/zbMATHOpen/zbmath-open-kg) | Pinned public JSONL sample or locally exported zbMATH JSONL | Public sample or authorized full export |
| [S2ORC](https://github.com/allenai/s2orc) | Semantic Scholar paper search AND local parsed S2ORC JSONL | Search is S2AG metadata, not S2ORC full text. Bulk needs dataset API access |
| [RealMath](https://github.com/ethz-spylab/RealMath) | Hugging Face public dataset split/rows API and local JSONL | Bounded public sample |
| [MathPile](https://github.com/GAIR-NLP/MathPile) | Streaming local JSONL/gzip | Gated, user must accept non-commercial and original-source restrictions |
| [mathlib4](https://github.com/leanprover-community/mathlib4) | Existing pinned complete corpus and FTS | Already indexed locally; no new import needed |

External source records are separate from the mandatory mathlib4/curated full index. Every cached record has original/project credit when supplied, source URL, dataset-specific locator, source snapshot fingerprint, rights status, paper name, author when known, DOI when supplied, record kind and proof status. Candidate selection does not verify or rediscover a theorem.

## Commands

From the repository root:

    python tools/knowledge_sources.py status
    python tools/knowledge_sources.py fetch theoremsearch "noncommutative Fourier estimates" --limit 8
    python tools/knowledge_sources.py fetch zbmath --limit 20
    python tools/knowledge_sources.py fetch s2orc "finite group representations" --limit 10
    python tools/knowledge_sources.py fetch realmath --limit 20

Network calls only occur from explicit fetch commands; ordinary MCTS is offline.
By default records go into the git-ignored .cache/math_mcts/literature.sqlite.

User-acquired licensed source exports:

    python tools/knowledge_sources.py import zbmath /path/to/zbmath.jsonl
    python tools/knowledge_sources.py import realmath /path/to/realmath.jsonl
    python tools/knowledge_sources.py import s2orc /path/to/s2orc.jsonl.gz
    python tools/knowledge_sources.py import s2orc /path/to/s2orc.jsonl.gz --include-text --ack-license
    python tools/knowledge_sources.py import mathpile /path/to/authorized/mathpile.jsonl.gz --ack-license

MathPile is a gated dataset and cannot be downloaded or used without accepting
its original non-commercial/data-source usage restrictions. Its data is licensed
CC BY-NC-SA 4.0 or stricter source terms, distinct from repository code license.
This adapter never circumvents the gate or downloads it for the user.
S2ORC uses the Semantic Scholar datasets API for bulk; its current
database-level license is ODC-By 1.0 and underlying papers may differ. Local
imports are bounded streaming batches; no external dataset is added to Git.

RealMath dataset fields include link, theorem, question, answer and context;
the adapter uses extracted theorem text, not model-produced answer. zbMATH
JSONL includes document_title, author, classification, review_text and doi
(often as arrays); its adapted records are bibliographic reviews, not proofs.
S2ORC local records are corpusid/externalids/content, optionally content.text.
MathPile rows contain text, SubSet and meta; original text authors and URLs
may be missing. These are marked 'unknown' rather than falsely attributed.

## Retrieval architecture

    python -m math_mcts research "spectral gaps on finite groups" --external-db .cache/math_mcts/literature.sqlite --iterations 1000 --depth 20

This uses the existing complete local SQLite FTS5 index plus a separate
read-only external FTS5 cache. The network is not called during MCTS.
MCTS re-queries at every expanded state. The fixed local corpus reserves
search slots and global exploration. External results first get a bounded
ID-only BM25 shortlist (up to 200 IDs), then fair round-robin across sources,
exact normalized-text duplicate suppression, and bounded record decoding
(default six external results per state). Query and card caches are bounded.

The full local index uses one bulk lookup per set of ranked rowids rather than
a SQL query for each row. No global Cartesian-product search is built.

Report fields:
- coverage.indexed_total: existing full pinned knowledge only
- coverage.external_candidates_indexed: actual external local cache size
- coverage.external_candidates_by_source: actual local cache per provider
- usage.distinct_external_lexical_hits: actually retrieved external records
- knowledge_records: cards and source/author/licensing provenance
- proof_verified: false for knowledge-selection paths

No claimed performance improvement until measured benchmarks. Retrieval
relevance is heuristic; no automatic semantic applicability or proof checks.

## Researcher credit and source restrictions

- mathlib4: Lean mathlib community, Apache-2.0; pinned SHA in
  ATTRIBUTION_AND_SOURCES.md. Contributors to modules are not necessarily
  historical mathematical theorem discoverers.
- TheoremSearch: https://www.theoremsearch.com/docs ;
  original paper authors, not the indexing platform, own original results.
- zbMATH Open KG: Yuni Susanti and Moritz Schubotz,
  arXiv:2609.00969; generated reviews/classifications CC BY-SA 4.0;
  some external abstract content restricted.
- S2ORC: Kyle Lo, Lucy Lu Wang, Mark Neumann, Rodney Kinney and Daniel
  Weld, ACL 2020; ODC-By 1.0 current corpus with additional original rights.
- RealMath: Jie Zhang, Cezara Petrui, Kristina Nikolić and Florian Tramèr,
  arXiv:2505.12575; original paper rights vary.
- MathPile: Zengzhi Wang, Xuefeng Li, Rui Xia and Pengfei Liu,
  NeurIPS Datasets & Benchmarks 2024; gated CC BY-NC-SA 4.0 or stricter.

Attribution is necessary, not sufficient for redistribution. No source is
promoted into trusted executable proof rules, rated difficulty, importance or
mathematical novelty automatically. Each user must separately review
hypotheses, original text, provenance, paper license and proof soundness.

## Test / release gate

    python tests/test_source_adapters.py
    python tests/test_literature_bridge.py
    python tests/test_indexed_mcts.py

Full GitHub CI must pass Python 3.10 and Python 3.12. No manifest version
changes, no invented imported counts, no G5C-specific assumptions and no
claimed universal speedup. Task branch is removed after merge.
