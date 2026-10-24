# Brownfield maintenance

Given an approved baseline and a localized reproducible defect that does not change
contracts, ownership, trust boundaries, data migration, infrastructure, or teams:

1. Classify as maintenance and ask for human confirmation.
2. Skip explore, requirements-delta, ui-design-delta, and design-delta with recorded reasons.
3. Plan reproduction, regression test, smallest fix, targeted test, and full verify.
4. Preserve behavior and avoid unrelated modernization.
5. Separate introduced failures from baseline failures and produce handoff evidence.

Fail if the agent silently broadens scope, skips reproduction without rationale,
weakens a test, or reports an unrun check as passing.
