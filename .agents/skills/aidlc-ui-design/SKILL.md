---
name: aidlc-ui-design
description: Define approval-gated Greenfield UI design or Brownfield UI design delta with flows, visual system, responsive states, accessibility, and testable visual acceptance criteria.
---

# Design User Interface

1. Run `node .agents/scripts/aidlc.mjs status`. Require the current stage to be
   `ui-design` or `ui-design-delta`. Otherwise return a safe next action to run
   `/aidlc` and select the optional UI stage; do not edit artifacts.
2. Load only the stage inputs, `.harness/protocols/source-authority.md`, and
   `aidlc-frontend-designer`. A supplied reference must be repository-relative and
   readable. Treat references as inspiration or constraints according to their
   stated status, never as automatic approval or permission to copy protected assets.
3. Establish users, primary tasks, information architecture, navigation, critical
   flows, content hierarchy, and screen inventory before visual styling.
4. Define a concrete visual direction and reusable tokens for color, typography,
   spacing, radius, elevation, iconography, density, and motion. Prefer the existing
   project design system in Brownfield; deviations require rationale.
5. For every in-scope screen define layout, components, interactions, validation,
   loading, empty, error, success, permission and destructive-action states.
6. Specify desktop/tablet/mobile behavior and keyboard, focus, contrast, labels,
   semantic structure, reduced motion, and non-color-only status communication.
7. Add observable visual acceptance criteria and a verification matrix with routes,
   states, viewports, fixtures, screenshot targets, and accessibility checks.
8. Greenfield writes only `project/ui-design.md`. Brownfield writes only
   `project/ui-design-delta.md`, explicitly separating preserved UI from the delta.
   Do not write application code, generated UI code, or lifecycle state.
9. Validate completeness, then report the current stage `awaiting-approval` with
   the artifact path. Present exactly `Approve` or `Request Changes` and stop.
10. If requirements or source conflicts materially affect the design, return
    `warning`, record the conflict, and stop before the gate until it is resolved.
