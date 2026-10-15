# Math-MCTS V7: 49-field coverage audit, grading queue, targeted supplementation and branch-diverse MCTS

## Scientific / curation contract

This phase audits **coverage of indexed mathematics records** and adds
unreviewed reusable mathematics proposals. It does NOT prove theorems, establish
historical priority/novelty, authenticate textbook citations, or certify a
curriculum's completeness.

Separate all of these:

1. **Historical source inventory**: `math_mcts/data/imported/manifest.json`
   has a declared bulk imported count; corpus text and sources have separate
   registration/audit pipelines.
2. **Module path index**: `module_index.json` contains module path prefixes.
   Counting paths is NOT counting mathematical statements or theorem proofs.
3. **Indexed 100k source view**: `classified_knowledge` has actual per-record
   source module, status, ungraded difficulty and separate importance fields.
4. **Edited catalog**: card difficulty and `核心/重要` editorial tags are
   NOT independently proved mathematics.
5. **AI supplements**: separate candidate pack + review-only grade suggestions.
   No AI-generated card automatically enters the curated catalog or RuleBook.
6. **Executable trusted rules**: only explicit reviewed formal premises, as
   checked by existing typed Horn/equational verifiers.

A theorem can belong to several branches. Field counts are therefore
multi-label and **must not be added to compute a unique total**.

## 49-field, 7-domain taxonomy

`math_mcts/data/field_taxonomy_v1.json` explicitly lists each field,
major-domain label, candidate source-module prefixes and lexical evidence terms.
Every field has a **human editorial review priority** P0/P1; this does
not indicate a theorem's objective importance.

A matched source prefix only establishes that a matching module path is indexed.
A curated title/branch match only establishes a lexical overlap—not true
mathematical categorization. When no 100k classified database is supplied,
`indexed_imported_records` is **null, never 0**.

Once the existing 100k classified index has been built, one grouped database
query retrieves real provenance-registered source counts, independent of
mathlib module-prefix counts. The result contains input provenance, duplicate
discipline warning, per-field graded/importance/verification-status *labels*,
real indexed cardinalities and a deterministic editorial work queue.
`independent_theorem_proof_count` remains unknown until a compatible
external proof audit has been performed.

```bash
python tools/audit_fields.py \
  --output field_audit_unindexed.json \
  --markdown field_audit_unindexed.md \
  --ai-pack examples/field_replenishment_v1.json

# After building and classifying the existing index:
python tools/audit_fields.py \
  --indexed-db math_index.sqlite \
  --output field_audit_100k.json \
  --markdown field_audit_100k.md \
  --ai-pack examples/field_replenishment_v1.json
```

**Important:** a P0 field with zero lexical catalog hits is not automatically
absent from raw mathlib or the whole body of mathematics; its review
queue simply has more work to perform.

## Targeted knowledge additions and grading

`examples/field_replenishment_v1.json`: **35** AI-authored, sourced as an
unverified knowledge pack, selected to span deep foundational and transferable
tools across logic, commutative/homological algebra, number theory, analysis,
geometry, probability, combinatorics, control and optimization.

Each entry has an explicit mathematical statement, hypotheses, conclusion,
proof strategy and falsification/reference-audit task. Examples include
the Yoneda lemma, Nakayama lemma, Plancherel theorem,
Sobolev/Poincaré estimate, Cauchy–Davenport, matroid basis greedy theorem,
Céa's lemma and the Kantorovich–Rubinstein duality.

These are **summaries of existing mathematics**; full references are deliberately
empty until individually checked, rather than fabricated. They are NOT novel
results or independently verified theorem proofs.

`math_mcts/data/field_level_review_suggestions_v1.json`: 35 separate
provisional Level 1–5 *review suggestions*. These suggestions are NOT
saved into the AI candidate records or the trusted curated catalog and cannot
be counted toward verified Level 1–4 expansion targets.

```bash
python tools/ai_knowledge_cli.py ingest \
  examples/field_replenishment_v1.json --db v7_ai_candidates.sqlite
python tools/ai_knowledge_cli.py inventory --db v7_ai_candidates.sqlite
```

## MCTS architecture review outcome

**Actual diagnosed bottleneck**: previous `CollisionProblem` enforced different
*major domain* for each paired concept, so two distinct research subfields
within algebra or analysis could never collide.

No rewrite of the independently checked Horn/equational proof engines is
needed to fix this. Instead the MCTS candidate sampler has a nonbreaking,
explicit **diversity axis**:

```python
from math_mcts.search import collide_concepts
from math_mcts.knowledge import KnowledgeTree
tree=KnowledgeTree.load()
# Original behavior remains unchanged:
a=collide_concepts(tree,iterations=600,diversity_axis="domain")
# New: allows different subfields inside the same major domain:
b=collide_concepts(tree,iterations=600,diversity_axis="branch")
```

The `branch` mode groups roots by `(domain,branch)` and excludes only
same-branch pairs (with same domain), allowing source-discipline bridges
like representation theory ↔ algebraic number theory.
It also weights such within-domain, cross-branch pairs by a small
*explicit heuristic*. The original `domain` mode is unchanged and
remains the default.

`math_mcts.ai_knowledge.collide_for_research` forwards this optional axis;
AI candidates stay untrusted on both paths. Collision is a **hypothesis
generation / exploration heuristic**, not a claim of proof or novelty.

The scope of this optimisation is candidate *reachability* and branch sampling,
not an asserted asymptotic runtime speedup. Full 100k search remains bounded
and may require separate retrieval/graph indexing for efficient repeated
trials.

## CI acceptance

- `python tests/test_field_inventory_v7.py` tests exact 49-field classification,
  path-vs-statement distinction, real SQLite record counts on a synthetic fixture,
  35 unreviewed AI cards, distinct grade-review suggestions, review queue
  reproducibility, unchanged original cross-domain search, newly accessible
  within-domain cross-branch MCTS pairing and invalid-axis rejection.
- Both Python 3.10 and 3.12 run new tests and unchanged legacy regressions.
- Python 3.12 repeats classification on the actual 100k source-index subset
  and publishes machine-readable `field_audit_100k.json` plus Markdown report.
- No modification of the single canonical `curated/manifest.json` version.
- No automatic upgrading of imported theorem statements or AI cards.

## Next review gates

Review P0 fields with demonstrably low confirmed curated content; retrieve
original theorem wording and proof sources; have an independent checker or
qualified reviewer verify statements and precise hypotheses before promoting.
Only afterward use their explicitly typed logical encodings as reviewed rules.
Increase field depth by robust coverage of *techniques and boundary cases*
rather than extrapolating a target number of statements.
