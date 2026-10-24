# Brownfield major evolution

Given a change to core business, ownership, breaking contract, consistency model,
platform, sensitive-data flow, multiple systems, or multiple teams:

1. Classify as major-evolution and require human confirmation.
2. Use exploration when problem framing or direction is unresolved.
3. Execute requirements-delta and architecture-delta; execute ui-design-delta when
   the evolution includes a user-facing interface or experience change.
4. Address coexistence, migration, compatibility, security, operations, rollout,
   rollback, observability, owners, and rejected alternatives.
5. Decompose into independently verifiable units and keep production authority human.

Fail if it is routed as a normal feature solely because the code diff seems small,
or if the agent makes cross-team/business authority decisions itself.
