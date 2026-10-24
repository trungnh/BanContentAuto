---
name: aidlc-brainstorm
description: Explore, diversify, compare, and narrow software project ideas before project/brief.md or AI-DLC state is initialized. Use when the developer has no project idea yet or only a broad problem area.
---

# Brainstorm Project Ideas

This skill normally runs before AI-DLC initialization. It may also run during an
unapproved Greenfield Discover stage, but never revises an approved artifact or a
Brownfield baseline/change. Do not change state, write application code, or select
a technology stack.

1. Read `project/idea-notes.md`, `project/specification-analysis.md`, and
   `.harness/protocols/source-authority.md`. If lifecycle state is active, require
   Greenfield Discover with no open/approved gate; otherwise stop with a safe retry.
2. Use the topic supplied with the invoking workflow as an optional starting
   domain, not a committed solution.
3. Ask at most three short questions at a time about:
   - domains or users the developer understands;
   - recurring problems worth solving;
   - available time, data, access, and constraints;
   - the kind of project they want to learn from or validate.
4. Diverge first: generate materially different problem/solution directions, not
   minor feature variants. For each, identify user, problem, value, required data,
   MVP size, and dominant risk.
5. Converge only after the developer asks: compare shortlisted ideas using explicit
   criteria and assumptions. Do not present a score as objective truth.
6. Write the exploration, shortlist, assumptions, rejected ideas, and open questions
   to `project/idea-notes.md`.
7. After the developer chooses a direction, offer to draft `project/brief.md` from
   the notes. Mark every unverified statement as an assumption.
8. End by recommending either another brainstorm round or review of the draft brief.
9. Treat specification statements as candidates or constraints according to their
   status. Record conflicts and require a user decision; never silently replace a
   specification or approved artifact with a brainstorm preference.
