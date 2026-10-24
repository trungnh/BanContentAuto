# Phase Boundary Governance

Before Construction:

- accepted requirements have observable criteria;
- design decisions trace to requirements or constraints;
- work units cover accepted requirements without dependency cycles;
- security, data, cost, and operational risks have owners or mitigations.
- for Brownfield, classification is human-confirmed, planned work is a delta from
  the approved baseline, and preserved behavior plus compatibility checks are explicit;
- a proposal has not overwritten the current-state baseline.

Before Operations:

- implemented requirements trace to code and actual verification;
- required checks ran and passed;
- skipped checks and known failures are explicit;
- deployment, rollback, observability, and incident ownership are defined;
- production approval is separate from build approval.

Before Brownfield Handoff:

- current and expected behavior trace to code and actual verification;
- introduced failures are absent and pre-existing failures are labeled separately;
- compatibility, migration, rollout, rollback, and residual risk are explicit when applicable;
- project baseline updates are proposals until the change is accepted as the new as-is state.

Write evidence to `project/evidence/phase-boundary-<phase>.md`.
