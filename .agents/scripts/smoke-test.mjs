import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const sourceRoot = process.cwd();
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "aidlc-smoke-"));
const script = path.join(sourceRoot, ".agents", "scripts", "aidlc.mjs");

const copy = (relative) => {
  const source = path.join(sourceRoot, relative);
  const target = path.join(tempRoot, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.cpSync(source, target, { recursive: true });
};

for (const item of [".agents", ".harness", "project/brief.md", "project/specification-analysis.md", "project/ui-design.md", "project/ui-design-delta.md", "project/evidence/visual-verification.md"]) copy(item);

const run = (...args) => {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: tempRoot,
    env: { ...process.env, AIDLC_ROOT: tempRoot },
    encoding: "utf8"
  });
  if (result.error) throw new Error(`Unable to spawn Node for smoke test: ${result.error.message}`);
  let body;
  try { body = JSON.parse(result.stdout); } catch { body = { raw: result.stdout, stderr: result.stderr }; }
  return { ...result, body };
};

try {
  assert.equal(run("validate").status, 0, "template validates");
  const graph = JSON.parse(fs.readFileSync(path.join(tempRoot, ".harness", "stage-graph.json"), "utf8"));
  assert.ok(graph.stages.find((stage) => stage.id === "discover").consumes.includes("project/specification-analysis.md"), "discover consumes normalized specification");
  const uiStage = graph.stages.find((stage) => stage.id === "ui-design");
  assert.equal(uiStage.mandatory, false, "UI design is optional");
  assert.equal(uiStage.gate, "human", "UI design requires human approval");
  assert.ok(graph.stages.findIndex((stage) => stage.id === "ui-design") < graph.stages.findIndex((stage) => stage.id === "plan"), "UI design precedes planning");
  assert.equal(run("init", "smoke-project").status, 0, "intent initializes");

  const discover = run("next");
  assert.equal(discover.status, 0, `next failed: ${JSON.stringify(discover.body)} ${discover.stderr || ""}`);
  assert.equal(discover.body.stage.id, "discover");

  assert.equal(run("report", "discover", "awaiting-approval", "project/context.md").status, 0);
  const selfApproval = run("approve");
  assert.notEqual(selfApproval.status, 0, "approval without a later human turn is rejected");

  fs.writeFileSync(
    path.join(tempRoot, ".harness", "state", "human-turn.json"),
    `${JSON.stringify({ recorded_at: new Date(Date.now() + 1000).toISOString(), session_id: "smoke", prompt_sha256: "smoke", decision: "approve" }, null, 2)}\n`
  );
  assert.equal(run("approve").status, 0, "approval after a human turn succeeds");

  const optional = run("next");
  assert.equal(optional.status, 0);
  assert.equal(optional.body.status, "warning");
  assert.match(optional.body.summary, /Selection required/);
  assert.equal(run("select", "elaborate", "skip", "brief is already testable").status, 0);

  const uiSelection = run("next");
  assert.match(uiSelection.body.summary, /ui-design/);
  assert.equal(run("select", "ui-design", "execute", "approved scope has a user-facing workflow").status, 0);
  assert.equal(run("next").body.stage.id, "ui-design");
  assert.equal(run("report", "ui-design", "awaiting-approval", "project/ui-design.md").status, 0);
  fs.writeFileSync(
    path.join(tempRoot, ".harness", "state", "human-turn.json"),
    `${JSON.stringify({ recorded_at: "2000-01-01T00:00:00.000Z", session_id: "stale", prompt_sha256: "stale", decision: "approve" }, null, 2)}\n`
  );
  assert.notEqual(run("approve").status, 0, "UI design cannot reuse an old human approval");

  process.stdout.write("AI-DLC smoke tests passed.\n");
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}
