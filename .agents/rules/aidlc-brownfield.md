---
description: Brownfield invariants for existing, released, inherited, legacy, or partially completed systems.
---

# AI-DLC Brownfield Rule

Apply when `.harness/project.json` uses `brownfield`. The legacy value
`brownfield-maintenance` is accepted only for backward compatibility.

- Treat the approved project baseline as the current-state authority; proposals
  belong in change-delta artifacts until accepted.
- Classify every change as maintenance, feature, or major-evolution before
  implementation. The agent proposes; a human confirms.
- Preserve behavior outside the approved delta. Prefer the smallest safe change
  and do not combine bug/CR delivery with unrelated cleanup or modernization.
- Do not infer a convention from one example. Label conclusions `CONFIRMED`,
  `INFERRED`, `INCONSISTENT`, or `UNKNOWN`; only confirmed conventions are musts.
- Bug fixes require reproduction and a regression test when practical.
  Characterization tests are appropriate when important current behavior lacks
  protection and the desired behavior is not yet authoritative.
- Public APIs, events, schemas, persisted data, configuration, and operational
  contracts are backward-compatible by default. Breaking changes require an
  approved delta, migration/coexistence plan, rollout, rollback, and owners.
- Never rewrite the approved baseline with a proposal. Update it only after the
  accepted change becomes the new as-is state.
- Stop on unknown business authority, production-only evidence, unsafe migration,
  irreproducible critical behavior, or a required check that cannot be interpreted.
