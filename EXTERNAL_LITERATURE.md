# External mathematical literature: author credit, permissions and hybrid retrieval

## Current scope

The **existing complete local Math-MCTS index remains mandatory** for standard
research. External literature is an **opt-in, local, unreviewed evidence tier**:
it never counts toward the complete mathlib/curated index, and cannot become
a reviewed proof rule by retrieval alone. The API is never called inside an
MCTS expansion. No network call is made by ordinary 'research' or 'collide'.

The connector uses TheoremSearch's documented
[GET /graph/embedding](https://www.theoremsearch.com/docs) endpoint, which
returns mathematical statements and paper-level metadata. We wrote our own
small standard-library client; we did **not** copy its code or training set.

Project and research credit:
- [TheoremSearch](https://github.com/uw-math-ai/TheoremSearch), by Luke
  Alexander, Eric Leonen, Sophie Szeto, Artemii Remizov, Ignacio Tejeda,
  Jarod Alper, Giovanni Inchiostro and Vasily Ilin (as listed in its repository).
- Citation from the upstream repository: *Semantic Search over 9 Million
  Mathematical Theorems*, 2026, arXiv:2602.05216.
- **Individual theorem credit belongs to the original cited authors, not
  automatically to the search platform or this repository.**
- The API supplies authors on some hits; absent authors remain unknown. The
  paper URL, title, source, external ID, remote statement ID, content snapshot
  digest, data-provider link and rights status stay on every cached candidate.

## Usage

Requires Python 3.10+ with SQLite FTS5. From the repository root:

    python tools/literature_search.py "compactness and noncommutative harmonic analysis" --limit 8
    python -m math_mcts research "compactness and noncommutative harmonic analysis" \
        --external-db .cache/math_mcts/literature.sqlite --iterations 120 --depth 8 \
        -o .cache/math_mcts/literature_research.json

The first command makes one bounded network request and caches accepted hits
in a separate, git-ignored SQLite DB. The second command is **offline**:
its primary complete index still checks all pinned imported manifests/hashes,
and it searches at most six external FTS hits per MCTS retrieval state alongside
the bounded primary search and primary random exploration. External hit counts
and actual selected source tiers are reported separately.

If using another locally supplied JSONL source, follow
'math_mcts.source_expansion.import_jsonl' and include full attribution and
explicit license information. Search candidates stay separate from curated
knowledge, with no automatic trust promotion.

## Index, ranking and limits

- **Primary**: mandatory complete fixed-source SQLite FTS5 index; unchanged.
- **External**: independent, read-only FTS5 candidate index, checked for count
  parity before use; 'source_expansion' owns atomic import and SHA256 IDs.
- **Merge**: reserve at least one primary hit, allocate at most six slots to
  local external BM25 hits, interleave by existing domain-balancing logic;
  do not allocate all-million cross-products.
- **Cache**: up to 128 external query-result keys and 512 decoded candidate
  cards kept in memory; all remote content remains in the ignored local DB.
- **Ranking**: existing MCTS heuristic is lexical/coherence/breadth, **not**
  proof applicability, novelty or validated semantic cross-field compatibility.
  API embedding ranking happens only at explicit prefetch time.
- **Coverage**: 'indexed_total' and 'complete_imported_index' continue to
  describe the original pinned corpus; 'external_candidates_indexed' is separate.
- **No speed claims**: code is structured for bounded lookup, but no benchmark
  speedup is asserted without end-to-end measurements.

## Licensing and provenance

**Attribution is necessary but not sufficient for redistribution.** Search
results may point to differently licensed papers and theorem compilations.
The local cache records 'license=unverified' and 'license_verified=false',
plus a no-redistribution policy. Do not commit the cache, republish retrieved
paragraphs, or put external text into public knowledge packs before verifying
the original source's reuse terms. TheoremSearch project source-code
licensing must also be checked separately if its code is ever reused.

Future optional sources are **not enabled automatically**:
- [zbMATH Open Knowledge Graph](https://github.com/zbMATHOpen/zbmath-open-kg):
  public KG content declared CC BY-SA 4.0; individual third-party abstracts
  may be unavailable because of different rights. Appropriate primarily for
  bibliography/MSC/relationship metadata and attribution.
- [MathPile](https://github.com/GAIR-NLP/MathPile): original corpus
  CC BY-NC-SA 4.0 or more restrictive original terms; commercial edition has
  different terms. Never assume bulk papers can be copied into this repo.
- [RealMath](https://github.com/ethz-spylab/RealMath): an independent
  source-extraction benchmark pipeline; reuse of its code/data is separately
  subject to its actual published license.

Engineering attribution and bibliographic credit are distinct from original
mathematical discovery. The method never labels its cached leads as proved,
important, original or authoritatively licensed. Independently validate
definitions, prerequisites, counterexamples, and proofs before use.
