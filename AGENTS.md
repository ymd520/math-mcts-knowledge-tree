# Repository operating rules

These rules apply whenever ChatGPT or another coding agent changes this repository.

## Version
- `math_mcts/version.py` is the only source of the current catalog/package version.
- Import the constant in code and tests. Do not copy the current version into the manifest, README, or test expectations.
- Historical release labels in `CHANGELOG.md` are immutable history; add new work under `Unreleased` unless a release is explicitly cut.

## Branch lifecycle
- Use one task branch for a change, named `task/<short-name>` (the current `textbook-based-*` prefix is also recognized by the cleanup workflow).
- Keep the branch while its pull request is open so the reviewed change remains updateable.
- `.github/workflows/delete-task-branch.yml` deletes same-repository `task/` and `textbook-based-` branches when their PR is closed, merged or abandoned. Remove other stale task branches once their work is integrated or abandoned.
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
