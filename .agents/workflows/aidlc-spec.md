---
description: Import and normalize a repository-local specification without treating it as approved authority or starting implementation.
---

# /aidlc-spec

Usage: `/aidlc-spec <repo-relative-path>`

1. Load `.agents/skills/aidlc-spec/SKILL.md`.
2. Pass the supplied path exactly as the specification source.
3. Produce `project/specification-analysis.md` and report the observation contract.
4. Do not advance lifecycle state or write application code.
