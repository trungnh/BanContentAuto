import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const sourceRoot = process.cwd();
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "aidlc-brownfield-"));
const script = path.join(sourceRoot, ".agents", "scripts", "aidlc.mjs");

const copy = (relative) => {
  const source = path.join(sourceRoot, relative);
  const target = path.join(tempRoot, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.cpSync(source, target, { recursive: true });
};

for (const item of [".agents", ".harness", "project"]) copy(item);

const run = (...args) => {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: tempRoot,
    env: { ...process.env, AIDLC_ROOT: tempRoot },
    encoding: "utf8"
  });
  let body;
  try { body = JSON.parse(result.stdout); } catch { body = { raw: result.stdout, stderr: result.stderr }; }
  return { ...result, body };
};

const approveCurrentGate = () => {
  fs.writeFileSync(
    path.join(tempRoot, ".harness", "state", "human-turn.json"),
    `${JSON.stringify({ recorded_at: new Date(Date.now() + 5000).toISOString(), prompt_sha256: `${Date.now()}`, decision: "approve" }, null, 2)}\n`
  );
  return run("approve");
};

try {
  assert.equal(run("validate").status, 0, "all profiles validate");
  assert.equal(run("init", "baseline-legacy-system", "brownfield-maintenance").status, 0, "legacy profile alias remains accepted");
  assert.equal(run("status").body.state.lifecycle_scope, "brownfield", "legacy profile alias normalizes to brownfield");

  assert.equal(run("next").body.stage.id, "baseline");
  assert.equal(run("report", "baseline", "awaiting-approval", "project/baseline.md").status, 0);
  assert.equal(approveCurrentGate().status, 0, "baseline approval succeeds");
  assert.equal(run("status").body.state.status, "complete", "baseline onboarding intent completes after approval");

  assert.equal(run("init", "legacy-bug-123", "brownfield").status, 0);
  assert.equal(run("next").body.stage.id, "classify");
  assert.equal(run("report", "classify", "awaiting-approval", "project/change.md").status, 0);
  assert.equal(approveCurrentGate().status, 0, "classification approval succeeds");

  for (const stage of ["explore", "requirements-delta", "ui-design-delta", "design-delta"]) {
    const selection = run("next");
    assert.match(selection.body.summary, new RegExp(stage));
    assert.equal(run("select", stage, "skip", "maintenance change has no trigger").status, 0);
  }

  assert.equal(run("next").body.stage.id, "plan");
  assert.equal(run("report", "plan", "awaiting-approval", "project/work-plan.md").status, 0);
  assert.equal(approveCurrentGate().status, 0, "plan approval succeeds");
  assert.equal(run("next").body.stage.id, "implement");
  assert.equal(run("report", "implement", "completed", "project/evidence/unit-result.md").status, 0);
  assert.equal(run("next").body.stage.id, "verify");
  assert.equal(run("report", "verify", "awaiting-approval", "project/evidence/verification.md").status, 0);
  assert.equal(approveCurrentGate().status, 0, "verification approval succeeds");
  assert.equal(run("next").body.stage.id, "handoff");
  assert.equal(run("report", "handoff", "completed", "project/evidence/handoff.md").status, 0);
  assert.equal(run("next").body.summary, "Workflow complete");

  const project = JSON.parse(fs.readFileSync(path.join(tempRoot, ".harness", "project.json"), "utf8"));
  assert.equal(project.project.baseline_status, "approved", "baseline approval is durable");

  assert.equal(run("init", "next-feature", "brownfield").status, 0);
  assert.equal(run("next").body.stage.id, "classify", "subsequent changes reuse approved baseline");
  process.stdout.write("AI-DLC Brownfield smoke tests passed.\n");
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}
