# Source Authority and Conflict Resolution

Use this protocol whenever brief, brainstorm, specification, repository evidence,
or user statements overlap.

## Authority order

1. The latest explicit user decision made with authority to decide the matter.
2. The latest applicable human-approved lifecycle artifact.
3. An explicitly approved external specification.
4. Draft `project/brief.md` and normalized specification candidates.
5. Brainstorm alternatives and exploration notes.
6. Agent inference.

Repository evidence is authoritative for observed Brownfield AS-IS behavior, but it
does not grant product authority or prove intended behavior. Laws, contracts, and
organizational policies remain external constraints and require an identified source.
Even a higher-authority new decision does not mutate an approved artifact silently;
the affected artifact must be revised and pass its human gate again before downstream use.

## Conflict handling

- Never silently merge contradictory statements or use recency alone to override
  an approved artifact.
- Record both claims, their sources, affected requirements/design/scope, and a
  recommended resolution.
- Mark the item `unresolved` until an authorized user decides or explicitly opens
  revision of the approved artifact.
- Block downstream work only when the unresolved conflict can materially change
  scope, acceptance criteria, architecture, security, data, compliance, or rollout.
- Preserve source traceability when promoting a candidate into a lifecycle artifact.
