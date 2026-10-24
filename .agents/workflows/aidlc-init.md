# Initialize AI-DLC

Initialize a lifecycle intent. Accept:

`/aidlc-init <intent-id> [greenfield|brownfield]`

If the ID is missing, ask for a 3–64 character kebab-case ID. If the profile is
missing, use `.harness/project.json`; ask only when repository state contradicts it.
Normally pass the profile explicitly for first-time onboarding, then omit it for
later intents in the same project.

1. Load `.agents/skills/aidlc-init/SKILL.md` and apply its profile-specific checks.
2. Run `node .agents/scripts/aidlc.mjs validate`.
3. Run `node .agents/scripts/aidlc.mjs init <intent-id> <profile>`.
4. Run `node .agents/scripts/aidlc.mjs status` and report the next action.
