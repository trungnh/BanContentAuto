# Harness Core Protocol

For each stage:

1. Ask the state utility for `next`; do not choose a different stage silently.
2. Read only the stage's declared inputs and relevant source files.
3. If an optional stage is undecided, select execute or skip with evidence and a
   reason before proceeding.
4. Produce all declared artifacts and verify every `done_when` statement.
5. Return observations with `status`, `summary`, `next_actions`, and `artifacts`.
6. On error also return `root_cause_hint`, `safe_retry`, and `stop_condition`.
7. For human gates, report `awaiting-approval`, present Approve/Request Changes,
   and wait for a new user turn before calling `approve` or `reject`.
8. Never edit `.harness/state/state.json` manually.

On interruption, read `.harness/protocols/recovery.md`. At phase boundaries, read
`.harness/protocols/governance.md`.

