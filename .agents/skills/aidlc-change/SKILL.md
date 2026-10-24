---
name: aidlc-change
description: Classify and conduct an existing-project bug fix, CR, feature, or major evolution through proportionate Brownfield stages. Use after an approved baseline.
---

# Conduct Brownfield Change

1. Confirm profile `brownfield` and an approved baseline.
2. Capture source, current behavior with evidence, expected behavior, acceptance
   criteria, scope, non-goals, unknowns, and blockers in `project/change.md`.
3. Propose exactly one class and let the human confirm:
   - `maintenance`: localized correction or compatible small change with no material
     boundary, core-domain, data-ownership, trust, infrastructure, or cross-team effect;
   - `feature`: new behavior within existing ownership/architecture, possibly with a
     compatible contract or migration and a requirement/design delta;
   - `major-evolution`: core business, boundary, ownership, breaking contract,
     consistency, platform, sensitive-data, multi-system, or multi-team change.
4. Recommend optional stages proportionately:
   - maintenance: normally skip explore, requirements-delta, ui-design-delta, and design-delta;
   - feature: execute only the stages triggered by behavior, UI, or architecture impact;
   - major-evolution: execute requirements-delta and design-delta, ui-design-delta
     when user-facing behavior changes, and explore when direction is unresolved.
   Select ui-design-delta for material screen, flow, navigation, component-state,
   responsive, accessibility, or design-system changes.
5. Security, production data, destructive migration, external write, and team/owner
   authority are gates, not reasons for the agent to broaden its own permissions.
6. Use `node .agents/scripts/aidlc.mjs select` for every optional-stage decision and
   record evidence plus reason. Never silently upgrade or downgrade the class.
7. Requirements and architecture artifacts describe only the delta. Keep the
   approved baseline unchanged until the accepted change becomes current state.
8. Plan the smallest safe units. Bug work starts with reproduction/regression
   strategy; poorly understood current behavior may require characterization.
9. Implement one approved unit at a time and verify against both the approved delta
   and preserved behavior. Separate pre-existing failures from introduced failures.
10. Handoff includes scope, evidence, compatibility, residual risk, human-owned next
    steps, and any baseline update proposed after acceptance.
