# Repository instructions

## Documentation placement

- Put user-facing documentation in `docs/`, grouped by subject where appropriate.
- Keep the root `README.md` as the concise project entry point, linking to detailed documents in `docs/`.
- Put implementation specifications and instructions intended for coding agents in `.agents/instructions/`.
- Do not place agent specifications in `docs/` or user-facing documentation in `.agents/`.

## Source of truth

- Treat `.agents/instructions/distributed-messaging-simulator-implementation.md` as the implementation source of truth until explicitly superseded.
- Keep documentation claims within the simulator's stated threat model. Do not claim proven anonymity, untraceability or production security.

## Project layout

- Put all Python application code, Python project metadata and Python tests under `python/`.
- Put the SvelteKit/Vite application and its JavaScript or TypeScript metadata under `web/`.
- Do not introduce `backend/` or `frontend/` application directories.

## Protocol fidelity

- A simulated node labelled with a named technology must implement the exact named and versioned algorithm selected by the specification, not a generic approximation.
- Expose the algorithm name, reference, parameters and documented simulation boundaries through API metadata so the UI can display them.
- Label incomplete or generic models explicitly as abstractions; never present them as faithful implementations of a named protocol.
