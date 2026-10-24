---
name: aidlc-release
description: Prepare and execute a reversible AI-DLC release with exact target, evidence, smoke tests, rollback, observability, and a separate real production approval.
---

# Release

1. Confirm the current stage is `release` and verification is approved.
2. Delegate readiness analysis to `aidlc-operator`; do not delegate approval.
3. Verify exact environment, artifact/version, owner, deployment steps, smoke tests,
   rollback trigger, rollback steps, dashboards, and alert ownership.
4. Open the release gate and end the turn.
5. Execute external or production mutation only after a new, explicit user approval
   and Antigravity's own permission prompt.
6. Record real deployment and smoke-test results in `project/evidence/release.md`.
7. Park immediately when rollback readiness or production identity is uncertain.

