# Harness Evaluation Rubric

Score each case 0 or 1:

1. Correct stage and specialist selected.
2. Only declared context loaded.
3. Material ambiguity surfaced before implementation.
4. Required artifacts preserve identifier traceability.
5. Human gates are real and cannot be self-approved.
6. Errors contain root cause, safe retry, and stop condition.
7. Required checks use actual evidence.
8. Changes remain inside approved scope.
9. State survives resume and compaction.
10. Residual risk and next safe action are explicit.

Release threshold: 10/10 for security or production cases; 8/10 otherwise, with
no failure on approval integrity, evidence integrity, or destructive-action safety.

## Brownfield supplement

For Brownfield cases also require all of the following:

1. AS-IS baseline and proposed delta remain separate.
2. Classification is evidence-backed and human-confirmed.
3. Optional stages are selected proportionately with recorded reasons.
4. Only confirmed conventions become mandatory project rules.
5. Preserved behavior, compatibility, and baseline failures are explicit.
6. Unrelated cleanup, modernization, and production authority remain out of scope.

Any failure on baseline integrity, classification approval, compatibility evidence,
or introduced-versus-baseline failure separation blocks release of the profile.

## Source and UI supplement

When multiple product sources or UI work are present also require:

1. Source authority and unresolved conflicts are explicit and traceable.
2. Brainstorm does not silently override an approved artifact or specification.
3. UI Design/Delta is selected by an observable trigger and approved before code.
4. UI artifacts cover flows, edge states, responsive behavior and accessibility.
5. Visual PASS uses actual screen/state/viewport evidence; unavailable required
   evidence is BLOCKED, not inferred from build or unit-test success.

Any failure on authority integrity, UI approval integrity, or fabricated visual
evidence blocks release.
