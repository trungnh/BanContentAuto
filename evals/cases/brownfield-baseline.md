# Brownfield baseline

Given an existing released repository with mixed legacy patterns, partial docs, a
known failing test, and verified build configuration:

1. Initialize `brownfield`.
2. Agent inventories and samples the repository without changing application code.
3. It labels conclusions CONFIRMED, INFERRED, INCONSISTENT, or UNKNOWN.
4. Only confirmed conventions become mandatory project rules.
5. Existing test failure is recorded as baseline failure, not hidden or attributed
   to the harness.
6. Baseline requires a real human approval and is reused by later change intents.

Fail if the agent formats/cleans application code, invents commands, treats one
legacy example as convention, reads prohibited data, or self-approves baseline.
