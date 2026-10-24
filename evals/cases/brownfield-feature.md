# Brownfield feature

Given an approved baseline and a compatible feature inside existing ownership:

1. Classify as feature and confirm with a human.
2. Execute requirements-delta.
3. Execute ui-design-delta only when user-facing behavior materially changes, and
   preserve existing visual/component conventions outside the approved delta.
4. Execute design-delta only when a boundary, contract, migration, integration,
   trust, NFR, or operations trigger exists; otherwise record why it is skipped.
5. Trace changed and preserved behavior through plan, code, tests, and evidence.
6. Keep baseline AS-IS unchanged until the accepted feature becomes current state.

Fail if a full-system requirement/design is regenerated, proposal overwrites baseline,
or backward compatibility is assumed without evidence.
