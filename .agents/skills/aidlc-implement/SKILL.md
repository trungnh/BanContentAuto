---
name: aidlc-implement
description: Implement one approved AI-DLC work unit with isolated context, targeted tests, scoped edits, actual evidence, and bounded recovery. Use during the implement stage.
---

# Implement Work Unit

1. Confirm `status` says the current stage is `implement`.
2. Read only the requested unit from `project/work-plan.md`, its requirement IDs,
   dependencies, design sections, dominant risk, and done condition.
3. Require a test strategy before code changes:
   - business logic, validation, parsing, and data transformations require unit tests;
   - bug fixes require a reproducing regression test when practical;
   - boundaries require the appropriate integration or contract test;
   - a unit-test exception requires a technical reason and deterministic alternative.
4. Delegate implementation to `aidlc-developer`. Include the work-unit ID supplied
   by the invoking workflow, exact input
   paths, allowed scope, configured commands, and evidence destination
   `project/evidence/unit-<UNIT-ID>.md`.
5. Ask `aidlc-quality-engineer` to independently verify the unit when its dominant
   risk is security, data integrity, concurrency, or an external contract.
6. Review the returned structured observation. A failed or unrun required check
   leaves the unit incomplete.
7. Do not mark the overall implement stage complete until every approved unit is
   complete and integrated.
