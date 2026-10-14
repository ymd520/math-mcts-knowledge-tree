# Evidence-first mathematics expansion (candidate sources + research actions)

This upgrade expands **usable candidates** without pretending that a large count
of imported declarations is a count of independent important theorems. It
does not claim to discover or prove any new mathematical result.

## 1. Real baseline before changing any catalog number

The original imported manifest, the active SQLite FTS index, the registered
source table, the classified table and the review table are **distinct**.
Do not add their counts together; their records can overlap.

```bash
python -m math_mcts info
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite
python tools/review_quality.py --db math_index.sqlite
python tools/expand_knowledge.py coverage --index math_index.sqlite
```

For broader *candidate coverage*, test a separately generated index with
`--candidate-limit 234576` **only where RAM, time and disk allow**. The source
manifest currently lists 234,576 imported records; this is an upper bound for
that particular import, not a claim that 234,576 unique, important or
kernel-verified theorems have been indexed. Full-scale index/CI performance
and deduplication must be measured; do not silently change the default.

## 2. Add new mathematical source collections safely

`math_mcts.source_expansion` implements an append-only candidate layer in a
**separate database**. It accepts human-prepared, permission-respecting
JSONL / JSONL.gz. It does **not** scrape arXiv, AFP, MathComp or textbooks.

Required JSON fields for **each line**:

| Field | Meaning |
|---|---|
| `source` | Upstream project or authored source label |
| `source_ref` | Pinned commit, release or explicit edition identifier |
| `source_url` | HTTPS source locator (no credentials) |
| `license` | Upstream license *claim*; not automatically validated |
| `locator` | Exact theorem/declaration identifier within the source/ref |
| `name` | Source theorem/knowledge name |
| `kind` | `theorem`, `lemma`, `definition`, `method`, `conjecture`, `counterexample` |
| `statement` | Concise mathematical statement or original summary |

Example **schema illustration only**, not a real imported theorem:

```json
{"source":"project-name","source_ref":"specific-version",
 "source_url":"https://example.org/source","license":"verify-before-reuse",
 "locator":"Module.TheoremName","name":"TheoremName",
 "kind":"theorem","statement":"Concise mathematical statement supplied by curator"}
```

```bash
python tools/expand_knowledge.py import --db external_math.sqlite --input candidate_sources.jsonl.gz
python tools/expand_knowledge.py inventory --db external_math.sqlite
python tools/expand_knowledge.py search --db external_math.sqlite --query "finite group"
```

### Data-integrity guarantees

- IDs bind `(source, source_ref, locator)` and exact statements carry SHA-256.
  Re-importing identical records is idempotent; the same locator/ref with
  changed contents rejects the entire transaction.
- The original source name, version and HTTPS locator remain attached.
  No source or license is independently authenticated by this importer.
- All newly imported records have `importance_status=unrated`,
  `difficulty_level=null`, `proof_verified_this_run=false`, and
  `license_verified=false`. Incoming claims of verification are ignored.
- Normalized-text duplicates are **flags**; no mathematical equivalence is
  inferred or automatically merged. A source match is not a proof.
- A separate SQLite file avoids destroying external additions when
  `math_index.sqlite` is rebuilt by the existing atomic index builder.
- Before importing substantial third-party datasets, independently check
  their terms and follow attribution/redistribution requirements.
  A mathematical fact may be freely described in independent words while
  protected prose, solutions or full text cannot automatically be copied.

## 3. Work on a specific bottleneck, not arbitrary term collisions

The existing Mathlib source registry and review signals can be filtered for
a research task, retaining the source statement fingerprint and warnings:

```bash
python tools/expand_knowledge.py prioritize --index math_index.sqlite \
  --focus "noncommutative convolution" --limit 40
python tools/expand_knowledge.py prioritize --index math_index.sqlite \
  --focus "finite group representation" --domain "代数" --limit 40
```

The ranking score is a **case-inspection heuristic**, comprising direct title
matches, module matches, the existing review priority and anomaly indicators.
It is not a predicted proof probability, intrinsic mathematical importance,
or a substitute for independent proof validation.

## 4. Mathematical method / obstacle library

`math_mcts.method_library` defines 31 explicitly stated mathematical actions
(covering proof strategies, representation changes, new invariants, extremal
bounds, counterexample attacks and verification). Every action has:

1. `requires`: preconditions that must be established for this problem.
2. `action`: an exploration step, not an automatic logical conclusion.
3. `proof_obligation`: what remains to prove before using an outcome.
4. `failure_test`: a deliberately adversarial test.
5. `category` and multilingual `triggers`: bounded retrieval only.

```bash
python tools/expand_knowledge.py methods --goal "noncommutative convolution upper bound"
python tools/expand_knowledge.py methods --goal "有限群卷积上界" \
  --obstacles "傅里叶 非交换 反例" --limit 20
```

These are candidate search actions for the *Discovery* side of MCTS; none is
installed into `RuleBook` as an axiom or claimed kernel-verified.
The *Verification* side must validate assumptions, test failure cases and
independently check proposed mathematical proofs.

## 5. Meaningful acceptance gates

```bash
python tests/test_expansion.py
python -m compileall -q math_mcts tools tests
```

The existing GitHub CI runs the expansion tests on Python 3.10 and 3.12.
Tests exercise duplicate flags, content tampering, source license/URL fields,
idempotence, full transaction rollback, no fake proof/grade promotion, targeted
method retrieval and guard against incorrectly promoted imported sources.

### Roadmap, not claimed as delivered

- Adapters that read real pinned AFP, MathComp and other original source
  formats with permission and verified licenses.
- Faithful translation of declarations into typed terms with explicit
  assumptions/conclusions and extraction evidence.
- Statement-level semantic equivalence audit and dependency graph edges,
  separately distinguished from mere lexical and source-reference edges.
- Verified operators integrated into MCTS actions with Lean kernel validation
  and independent falsification, tested against BFS/beam on held-out research
  problems.
- Quality-controlled editorial promotion with statement-specific references,
  no fixed quotas per education level and reproducible audit signatures.

**Version rule:** do not modify versions in prose or random source files.
The canonical version location remains the repository manifest; this change
does not assert a new catalog version or change its number.
