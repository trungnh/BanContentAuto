# Recovery Protocol

1. Run `node .agents/scripts/aidlc.mjs validate` and `status`.
2. Classify the failure as input, tool, implementation, verification, or policy.
3. Preserve raw failure evidence before a fix.
4. Retry only when safe and the root-cause hypothesis changed.
5. Stop at the configured retry limit or immediately at a policy boundary.
6. Never bypass tests, weaken assertions, disable security, fabricate approval,
   or silently skip a required check.
7. Use `park` when progress cannot continue safely.
