# Conduct AI-DLC Stage

1. Load `.agents/skills/aidlc/SKILL.md` and follow it completely.
2. Use `node .agents/scripts/aidlc.mjs` for every state transition.
3. When the directive names `mode: subagent`, invoke the named custom subagent
   with exact inputs, outputs, scope, done conditions and observation contract.
4. For a human gate, present only `Approve` or `Request Changes`, stop and wait
   for a new human turn.
