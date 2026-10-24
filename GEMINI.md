# Project Agent Instructions

## Mission

Deliver the smallest verified change that advances the approved product intent.
Preserve traceability from intent to requirement, work unit, code, and evidence.

## Startup contract

Before changing application code:

1. Read `.harness/state/state.json` if it exists.
2. Read `.harness/project.yaml`.
3. Load only the current stage and the artifacts it consumes.
4. State assumptions that affect scope, architecture, security, cost, or data.
5. Stop for human input when an unresolved choice would materially change the result.

For a new repository, use the `orchestrate-project` skill. For an approved work
unit, use `implement-unit`. For release decisions, use `verify-release`.

## Engineering rules

- Define observable completion criteria before implementation.
- Prefer tests that reproduce behavior before changing behavior.
- Make surgical changes; do not refactor unrelated code.
- Do not invent requirements, credentials, production data, or external approvals.
- Keep application code outside `project/` and `.harness/`.
- Record architectural or product decisions in `project/decisions.md`.
- Store actual verification output or a faithful summary in `project/evidence/`.
- A failing required check is never a successful completion.

## Approval policy

Human approval is required before:

- accepting product requirements or architecture;
- destructive or irreversible data changes;
- modifying authentication, authorization, secrets, or permissions;
- spending material external resources;
- writing to production or sending external communications;
- releasing to production.

Approval must come from a real user turn. The agent may not approve its own work.

## Completion report

Report:

- outcome and acceptance criteria satisfied;
- files and artifacts changed;
- checks run with actual pass/fail results;
- assumptions, skipped checks, and residual risks;
- the next safe action.

