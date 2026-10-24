---
name: aidlc-init
description: Initialize an AI-DLC intent with the greenfield or brownfield profile. Use when starting this harness for the first time or onboarding an existing project.
---

# Initialize AI-DLC

1. Determine the profile. Use `greenfield` for a new system and
   `brownfield` for an existing, released, inherited, partially built,
   or legacy system. Do not infer greenfield merely because documentation is empty.
2. Read `project/brief.md`. For greenfield, require intent, success measures and
   constraints. For brownfield, require repository identity, onboarding purpose,
   maintenance scope and known safety constraints; unknown product details may be
   discovered during baseline.
3. Run `node .agents/scripts/aidlc.mjs validate`.
4. Run `node .agents/scripts/aidlc.mjs init <intent-id> <profile>` using the ID and
   profile supplied by the invoking workflow.
5. Run `node .agents/scripts/aidlc.mjs next`.
6. Follow the returned stage contract. Do not write application code during
   Greenfield Discover or Brownfield Baseline.
