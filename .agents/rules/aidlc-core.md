---
description: Always-on AI-DLC lifecycle invariants for this workspace.
---

# AI-DLC Core Rule

@.harness/protocols/core.md

- Run `/aidlc-status` before lifecycle work and treat `.harness/state/state.json`
  as the source of truth.
- Use workflows to change lifecycle state; never edit state JSON manually.
- Load only the current stage, declared artifacts, and relevant skill/agent.
- Deliver the smallest verified change that advances approved intent.
- Never invent requirements, credentials, evidence, production data, or approval. Do not use generic placeholders for artifacts. 
- In the PLAN stage (for both Greenfield and Brownfield), NEVER write a generic or superficial work plan. You MUST detail concrete technical solutions (exact files, functions, and architectures). For bugs, you MUST first read the codebase to find the exact root cause. Never request approval on a superficial plan.
- Never invent requirements, credentials, evidence, production data, or approval.
- Never weaken tests or security controls to create a passing result.
- A failed or unrun required check is not success.
- Record actual commands and results in `project/evidence/`.
- Require real human approval at every declared human gate. An agent or subagent
  cannot approve its own output.
- Report status, summary, next actions, artifacts, skipped checks and residual
  risks according to `.harness/contracts/observation.schema.json`.
