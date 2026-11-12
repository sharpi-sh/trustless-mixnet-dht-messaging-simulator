# Repository instructions

## Documentation placement

- Put user-facing documentation in `docs/`, grouped by subject where appropriate.
- Keep the root `README.md` as the concise project entry point, linking to detailed documents in `docs/`.
- Put implementation specifications and instructions intended for coding agents in `.agents/instructions/`.
- Do not place agent specifications in `docs/` or user-facing documentation in `.agents/`.

## Source of truth

- Treat `.agents/instructions/distributed-messaging-simulator-implementation.md` as the implementation source of truth until explicitly superseded.
- Keep documentation claims within the simulator's stated threat model. Do not claim proven anonymity, untraceability or production security.
