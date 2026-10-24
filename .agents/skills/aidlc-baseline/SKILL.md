---
name: aidlc-baseline
description: Discover and baseline an existing project before AI-assisted maintenance, feature, or major-evolution work. Use only for the brownfield baseline stage.
---

# Baseline Existing Project

1. Confirm state profile `brownfield` and current stage `baseline`.
2. Read the brief, repository documentation, dependency/build manifests, CI,
   source/test trees, configuration, contracts, migrations, operations material,
   and existing harness files. Never read known secret or production-data paths.
3. Inventory first, then sample representative implementations from active modules
   and layers. Record coverage and gaps; do not claim the whole repository was
   reviewed when sampling was used.
4. Establish evidence-backed technology versions, module map, dependency direction,
   entry points, contracts, build/test commands, operations constraints, generated
   files, baseline failures, and high-risk boundaries.
5. For each conclusion use exactly one confidence label:
   - `CONFIRMED`: enforced configuration/documentation or repeated consistent evidence;
   - `INFERRED`: at least two independent clues but no authority;
   - `INCONSISTENT`: competing patterns exist;
   - `UNKNOWN`: evidence is insufficient or inaccessible.
6. Resolve conflicts in this order: enforced config/approved ADR, maintained recent
   code, repeated active-module pattern, then owner decision. Never convert inferred
   or inconsistent behavior into a mandatory rule.
7. Before write, present a baseline plan containing evidence coverage, proposed
   artifacts, project rules, commands to verify, unknowns, and excluded areas.
8. Write only baseline/harness artifacts after the user accepts that plan. Do not
   edit, format, upgrade, or clean application code.
9. Populate `project/baseline.md`, `context.md`, `architecture.md`, `operations.md`,
   and `.harness/project.json`. Create only the project rules justified by confirmed
   evidence, using the Brownfield profile templates as structure.
10. Run harness validation and only safe project checks whose commands were verified.
    Record command, exit code, environment limitation, and pre-existing failures.
11. Report `baseline awaiting-approval` with all artifacts. Baseline approval is a
    lifecycle gate; never approve it yourself. Approval completes this onboarding
    intent. The next change must start with a new Brownfield intent and reuses the
    durable approved baseline.
