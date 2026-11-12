Execute the complete one-shot build of the Trustless Mixnet DHT Messaging Simulator.

Canonical repository: "trustless-mixnet-dht-messaging-simulator"

Before implementation:

1. Read and follow AGENTS.md.
2. Read any local-only guidance under .agents/local/.
3. Read .agents/instructions/distributed-messaging-simulator-implementation.md completely.
4. Inspect and preserve all existing uncommitted changes.
5. Verify repository root, branch, remote, worktrees and status.
6. Create or switch to the development branch from the current HEAD.
7. Commit the existing intended documentation and instruction changes using the required JMBP21 commit format.

Implementation workflow:

- Derive bounded features from the specification phases.
- Create each feature from updated development as feature/<kebab-case-name>.
- Write tests alongside each logical increment.
- Commit the implementation checkpoint before confirmation testing.
- Run focused and affected integration tests.
- Fix failures and repeat until expected output is confirmed.
- Make the post-verification commit with exact test results.
- Merge the verified feature into development using a non-fast-forward merge.
- Start the next feature from the newly updated development branch.
- Continue until the full specification and definition of done are implemented.

Requirements:

- Python application and tests live under python/.
- SvelteKit/Vite application lives under web/.
- Python remains authoritative for every simulation decision.
- Implement the specified Loopix 2017 and Kademlia 2002 profiles faithfully.
- Preserve all protocol-fidelity labels and security limitations.
- Implement SimulationStep, NetworkPath and inert GlobalObserver objects.
- Implement staged messages, polling controls, runtime route blocking, device logs and cryptographic lineage.
- Implement the constrained D3 column layout, upper forward lane, lower reply lane and path-transit animation.
- Use the repository visual references without copying them directly.
- Initialise the local Graphify index after indexed source code exists and refresh it after committed source or schema changes.
- Do not use Vercel.
- Do not stop after scaffolding or partial visual representations.
- Do not claim completion until unit, integration, frontend and end-to-end tests pass.

Final verification on development:

- Run all test suites, linting, type-checking and coverage.
- Start Python and the web client independently.
- Execute the complete Alice-to-Bob-to-Alice acceptance flow.
- Verify failures, retries, polling toggles, blocked paths, transit delays, message editing, device logs and key lineage.
- Confirm Graphify is current.
- Report commits, merges, exact test results, coverage and unresolved protocol decisions.
- Leave development as the complete verified one-shot build branch.

## Build objective and evidence

Establish the complete one-shot build as an active objective before implementation. Keep the objective active through feature integration and final verification on `development`. Mark it complete once the definition of done has been verified and the HTML build report is available.

Record the build start time and maintain a chronological milestone log. For each milestone, capture its start and finish, elapsed time, feature branch, implementation and verification commits, merge commit and outcome. Record the role and scope of each sub-agent, the work it delivered and how that work was verified. Distinguish concurrent work from sequential work when calculating elapsed time.

Retain the commands, exit statuses and output from unit, integration, frontend, end-to-end, linting, type-checking and coverage runs. Include material failures, their corrections and the successful reruns. Identify any timing reconstructed from Git history and any verification that could not be completed.

At handover, provide a standalone HTML build report under `docs/reports/`. Include the milestone timeline, total wall-clock duration, sub-agent contributions, recorded test output and coverage, final acceptance results, Graphify status and outstanding protocol decisions. Link the report from the final response.
