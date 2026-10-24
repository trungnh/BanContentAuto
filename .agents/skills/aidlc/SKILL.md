---
name: aidlc
description: Conduct the current AI-DLC lifecycle stage, resume workflow state, select optional stages, dispatch scoped subagents, validate artifacts, and enforce human approval gates. Use for any project lifecycle advancement.
---

# AI-DLC Conductor

1. Run `node .agents/scripts/aidlc.mjs validate` and then `status`.
2. If parked, read `.harness/protocols/recovery.md`; do not auto-resume an
   unresolved blocker.
3. Run `next` and obey the returned directive.
4. When optional-stage selection is requested, assess the stage condition from
   approved artifacts, state the evidence, and run:

   `node .agents/scripts/aidlc.mjs select <stage> execute|skip <reason>`

5. Load only the returned stage inputs and the lead agent definition.
   When inputs contain multiple product sources, also load
   `.harness/protocols/source-authority.md` and apply it before synthesis.
   When the profile is Brownfield, also load `.agents/rules/aidlc-brownfield.md`
   and the approved project-specific rules relevant to the change.
6. For `mode: subagent`, delegate to the named project subagent with the stage,
   exact artifact paths, done conditions, and observation contract. Do not give it
   authority to resolve human gates.
7. Validate all produced artifacts and `done_when` conditions.
8. For a stage without a gate, run:

   `node .agents/scripts/aidlc.mjs report <stage> completed <evidence paths>`

9. For a human gate, run:

   `node .agents/scripts/aidlc.mjs report <stage> awaiting-approval <artifact paths>`

   Present exactly: Approve or Request Changes. End the turn and wait.

10. On the next real user turn, translate their actual response to `approve` or
    `reject <feedback>`. Never infer approval from silence or from your own text.
11. At Inception/Change Inception → Construction and Construction →
    Operations/Handoff, load and apply `.harness/protocols/governance.md` before
    opening the gate.
