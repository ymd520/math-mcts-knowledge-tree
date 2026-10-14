# Repository operating rules

These rules apply whenever ChatGPT or another coding agent changes this repository.

## Version
- `math_mcts/data/curated/manifest.json` is the only source of the current catalog/package version. Runtime code may expose a derived accessor, but version edits belong only in the manifest.
- Runtime code and tests must read the version from the manifest-derived accessor. Update the current version only in the manifest; do not duplicate it in README text or test expectations.
- Historical release labels in `CHANGELOG.md` are immutable history; add new work under `Unreleased` unless a release is explicitly cut.

## Branch lifecycle
- Use one task branch for a change, named `task/<short-name>` (the current `textbook-based-*` prefix is also recognized by the cleanup workflow).
- Keep the branch while its pull request is open so the reviewed change remains updateable.
- `.github/workflows/delete-task-branch.yml` deletes same-repository `task/` and `textbook-based-` branches immediately after their PR is merged. Closing an unmerged PR does not delete its branch. Remove other stale task branches once their work is integrated or abandoned.
- Before cleanup, verify that every intended change is committed and preserved in the pull request or target branch.

## Numerical claims and documentation
- Calculate counts from the current catalog or reproducible build output before editing documentation.
- Run the relevant inventory command and tests; record the command and computed result in the change summary.
- Never estimate totals by eye, carry forward stale README counts, or report planned rows as written rows.
- If a quantity cannot be reproduced, mark it unknown instead of presenting an estimate.

## Textbook research and knowledge cards
- Prefer primary, official textbook or course sources. Record author/title, edition where known, source URL, chapter/section locator, access and license status, and what the source supports.
- Write concise original mathematical summaries. Do not copy textbook prose, examples, exercises, or solution text into cards.
- Respect source-specific AI and reuse terms. In particular, do not ingest OpenStax textbook content into an LLM or derive cards from it without the written permission required by its published terms.
- Keep importance, difficulty, source attribution, editorial review, and formal proof status separate. A textbook citation alone is not proof verification.
- Do not mark a card as formally proved or independently verified without the corresponding review.
- State accurately whether a feature uses MCTS, exact ranking, or another retrieval method.
