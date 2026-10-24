import fs from "node:fs";
import path from "node:path";

let input = "";
for await (const chunk of process.stdin) input += chunk;
let event = {};
try { event = input ? JSON.parse(input) : {}; } catch { process.exit(0); }
const args = event.toolCall?.args || event.tool_input || {};
const changed = args.file_path || args.FilePath || args.path || args.Path || "";
if (!changed.includes(`${path.sep}.harness${path.sep}`) && !changed.includes("/.harness/")) process.exit(0);
try {
  const statePath = path.join(process.cwd(), ".harness", "state", "state.json");
  const graphPath = path.join(process.cwd(), ".harness", "stage-graph.json");
  const brownfieldGraphPath = path.join(process.cwd(), ".harness", "profiles", "brownfield", "stage-graph.json");
  const projectPath = path.join(process.cwd(), ".harness", "project.json");
  JSON.parse(fs.readFileSync(statePath, "utf8"));
  JSON.parse(fs.readFileSync(graphPath, "utf8"));
  JSON.parse(fs.readFileSync(brownfieldGraphPath, "utf8"));
  JSON.parse(fs.readFileSync(projectPath, "utf8"));
  process.stdout.write(JSON.stringify({ injectSteps: [{ ephemeralMessage: "AI-DLC harness JSON remains parseable after the write." }] }));
} catch (error) {
  process.stdout.write(JSON.stringify({
    injectSteps: [{ ephemeralMessage: `HARNESS ERROR: JSON validation failed after write: ${error.message}. Repair it before continuing.` }]
  }));
}
