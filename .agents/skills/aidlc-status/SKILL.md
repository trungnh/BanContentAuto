---
name: aidlc-status
description: Show the durable AI-DLC workflow status and the next safe action without changing application code or lifecycle state. Use after resume, compaction, or when asked for progress.
---

Run `node .agents/scripts/aidlc.mjs validate` followed by
`node .agents/scripts/aidlc.mjs status`. Summarize the current intent, stage, open
gate, blocker, last evidence, and next safe command. Do not advance the workflow.

