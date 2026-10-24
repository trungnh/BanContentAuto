let raw = "";
for await (const chunk of process.stdin) raw += chunk;
let event = {};
try { event = raw ? JSON.parse(raw) : {}; } catch { event = {}; }

const args = event.toolCall?.args || {};
const command = String(args.CommandLine || args.command || args.cmd || "");
const risky = /\b(git\s+push|terraform\s+apply|tofu\s+apply|kubectl\s+(apply|delete)|helm\s+upgrade|DROP\s+(TABLE|DATABASE)|DELETE\s+FROM)\b/i;

if (risky.test(command)) {
  process.stdout.write(JSON.stringify({
    decision: "force_ask",
    reason: "AI-DLC requires explicit tool permission for external, destructive, infrastructure, or production-affecting commands. Lifecycle approval remains a separate gate."
  }));
} else {
  process.stdout.write(JSON.stringify({
    decision: "ask",
    reason: "Review terminal commands during AI-DLC execution. Add narrowly scoped project permission rules only after the command is understood and trusted."
  }));
}
