---
name: aidlc-verify
description: Independently verify implementation against requirements, quality gates, security expectations, traceability, and operational readiness before a release decision.
---

# Verify Release Candidate

1. Confirm the current stage is `verify`.
2. Delegate to `aidlc-quality-engineer` with requirements, work plan, configured
   commands, unit evidence, and changed application files.
3. For identity, permissions, secrets, sensitive data, or supply-chain changes,
   also delegate a focused pass to `aidlc-security-engineer`.
4. Require a requirement → code → test/evidence table.
5. Preserve actual command output and exit status in
   `project/evidence/verification.md`.
6. Treat unset, skipped, unrun, or failed required checks according to project
   policy; never silently turn them into PASS.
7. When the current intent has an approved `ui-design` or `ui-design-delta` gate,
   verify every required
   screen/state/viewport using actual screenshots or configured browser evidence
   plus applicable accessibility checks. Write
   `project/evidence/visual-verification.md`. If required tooling, fixtures, routes,
   or a reviewable environment are unavailable, report BLOCKED, not PASS.
8. Apply Construction → Operations governance and open the verify human gate.
