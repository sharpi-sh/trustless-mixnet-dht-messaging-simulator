# Repository instructions

## Documentation placement

- Put user-facing documentation in `docs/`, grouped by subject where appropriate.
- Keep the root `README.md` as the concise project entry point, linking to detailed documents in `docs/`.
- Put implementation specifications and instructions intended for coding agents in `.agents/instructions/`.
- Do not place agent specifications in `docs/` or user-facing documentation in `.agents/`.

## Source of truth

- Treat `.agents/instructions/distributed-messaging-simulator-implementation.md` as the implementation source of truth until explicitly superseded.
- Keep documentation claims within the simulator's stated threat model. Do not claim proven anonymity, untraceability or production security.
- Before project work, read any local-only guidance under `.agents/local/` when present. Its absence is normal.

## Project layout

- Put all Python application code, Python project metadata and Python tests under `python/`.
- Put the SvelteKit/Vite application and its JavaScript or TypeScript metadata under `web/`.
- Do not introduce `backend/` or `frontend/` application directories.

## Protocol fidelity

- A simulated node labelled with a named technology must implement the exact named and versioned algorithm selected by the specification, not a generic approximation.
- Expose the algorithm name, reference, parameters and documented simulation boundaries through API metadata so the UI can display them.
- Label incomplete or generic models explicitly as abstractions; never present them as faithful implementations of a named protocol.

## Implementation segmentation

- Derive implementation segments from the phases and checklists in `.agents/instructions/distributed-messaging-simulator-implementation.md`.
- Treat each coherent application part as a separate feature. Do not generate the entire application as one unstructured change.
- Break every feature into small logical increments with an explicit expected output and focused test boundary.
- A logical increment is not complete until its focused tests pass and its observable output has been inspected.

## Execution and model-routing directive

Operate as an engineering orchestrator. Optimise for speed, cost and correctness by delegating work selectively and matching model capability to task complexity.

### Task decomposition and delegation

- Break multi-file or multi-stage work into clearly bounded subtasks before implementation.
- Run independent, non-blocking subtasks concurrently when sub-agents are available.
- Delegate only when parallelism or specialist analysis provides a clear benefit.
- Give each sub-agent the minimum relevant context, explicit scope, expected output and verification criteria.
- Keep ownership clear when multiple agents share the workspace to prevent conflicting edits.
- Complete tightly coupled or trivial work directly rather than delegating it.

### Model and reasoning selection

Use the least expensive capable model and lowest sufficient reasoning effort. Select from models actually available in the current environment; do not depend on hard-coded model names.

| Complexity | Model tier | Reasoning effort | Typical work |
|---|---|---|---|
| Simple | Fast or budget | Minimum | File inspection, searches, formatting, linting, boilerplate and basic documentation checks |
| Moderate | General-purpose | Low to medium | Unit tests, routine refactoring, API handlers and localised feature implementation |
| Complex | Frontier or reasoning | High | Architecture, security analysis, concurrency defects and cross-system refactoring |

Task percentages and token ranges are guidance, not quotas. Increase capability only when evidence shows it is necessary.

### Execution rules

- Begin useful work immediately; avoid conversational filler and unnecessary status updates.
- Preserve applicable repository instructions, protection gates and user-approval requirements.
- Do not delegate destructive, security-sensitive or approval-gated actions unless explicitly authorised.
- If a delegated subtask fails verification twice for the same reason, reassess its instructions and escalate only that subtask's model tier or reasoning effort.
- Treat failures caused by missing access, unclear requirements or environmental problems as blockers rather than model failures.
- Reconcile all outputs centrally. Review overlapping changes before integration.
- Apply deterministic patches where practical and preserve unrelated existing work.
- Verify the integrated result with the most relevant available checks.
- Report only material changes, verification results, unresolved risks and required user decisions.

## Branch workflow

- `development` is the canonical integration branch and the branch on which the final one-shot build and complete end-to-end verification are produced.
- Start every application feature from the latest verified `development` commit using a Git-valid branch named `feature/<kebab-case-name>`; Git branch names cannot begin with `/`.
- Implement and verify only that feature on its branch.
- After the feature's focused and affected integration tests pass, merge it back into `development` with a non-fast-forward merge so the feature boundary remains visible.
- Create the next `feature/<name>` branch from the newly updated `development` branch, not from the preceding feature branch.
- Do not merge an incomplete or failing feature into `development`.
- Do not use `main` as the implementation integration branch unless the human explicitly changes this workflow.

## Commit and verification workflow

For every logical increment on a feature branch:

1. Write or update the focused tests alongside the implementation.
2. Commit the logical implementation checkpoint before running its confirmation test pass.
3. Run the focused tests, inspect expected output and run affected integration tests.
4. Fix failures and repeat testing until the increment works as specified.
5. Commit the verified state after confirmation. Include fixes, final tests or verification-report changes. If testing produces no file change, an empty verification commit is permitted so long as its body records the exact commands and passing results.

Do not defer tests to the end of a feature, phase or full build. At feature completion, run the complete relevant test set, record coverage where available and make the final verification commit before merging to `development`.

All commits use:

```text
JMBP21 Codex {model}: {concise subject}

Model: {model and effort}
Message:
- {feature or verification details}
- {tests and results where applicable}
```
