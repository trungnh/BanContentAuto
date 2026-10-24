import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

let raw = "";
for await (const chunk of process.stdin) raw += chunk;
let event = {};
try { event = raw ? JSON.parse(raw) : {}; } catch { event = {}; }

const root = event.workspacePaths?.[0] || process.cwd();
const statePath = path.join(root, ".harness", "state", "state.json");
const turnPath = path.join(root, ".harness", "state", "human-turn.json");
const approvals = new Set(["approve", "approved", "yes", "phê duyệt", "đồng ý", "chấp thuận"]);

function userText(value) {
  if (!value || typeof value !== "object") return null;
  const role = String(value.role || value.author || value.type || "").toLowerCase();
  if (role === "user" || role === "human" || role === "user_message") {
    for (const key of ["content", "text", "message", "prompt"]) {
      if (typeof value[key] === "string" && value[key].trim()) return value[key].trim();
      if (Array.isArray(value[key])) {
        const joined = value[key].map((item) => typeof item === "string" ? item : item?.text || "").join(" ").trim();
        if (joined) return joined;
      }
    }
  }
  for (const child of Object.values(value)) {
    const found = Array.isArray(child)
      ? child.map(userText).filter(Boolean).at(-1)
      : userText(child);
    if (found) return found;
  }
  return null;
}

let latestPrompt = null;
if (event.transcriptPath && fs.existsSync(event.transcriptPath)) {
  for (const line of fs.readFileSync(event.transcriptPath, "utf8").split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const found = userText(JSON.parse(line));
      if (found) latestPrompt = found;
    } catch { /* Ignore partial transcript lines. */ }
  }
}

if (latestPrompt) {
  const hash = crypto.createHash("sha256").update(latestPrompt).digest("hex");
  let previous = {};
  try { previous = JSON.parse(fs.readFileSync(turnPath, "utf8")); } catch { previous = {}; }
  if (previous.prompt_sha256 !== hash) {
    const normalized = latestPrompt.toLocaleLowerCase("vi-VN").replace(/[.!]+$/g, "").trim();
    fs.mkdirSync(path.dirname(turnPath), { recursive: true });
    fs.writeFileSync(turnPath, `${JSON.stringify({
      recorded_at: new Date().toISOString(),
      conversation_id: event.conversationId || null,
      prompt_sha256: hash,
      decision: approvals.has(normalized) ? "approve" : "feedback"
    }, null, 2)}\n`);
  }
}

let message = "AI-DLC warning: state.json is missing. Run validation before lifecycle work.";
try {
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
  message = state.status === "uninitialized"
    ? "AI-DLC is uninitialized. Fill project/brief.md and run /aidlc-init <intent-id> [greenfield|brownfield]."
    : `AI-DLC state: ${state.status}; profile: ${state.lifecycle_scope || "legacy"}; current stage: ${state.current_stage || "none"}; awaiting: ${state.awaiting?.stage || "none"}. Use /aidlc-status before lifecycle work.`;
} catch { /* Keep warning. */ }

process.stdout.write(JSON.stringify({ injectSteps: [{ ephemeralMessage: message }] }));
