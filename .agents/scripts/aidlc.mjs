import fs from "node:fs";
import path from "node:path";

const root = process.env.AIDLC_ROOT ? path.resolve(process.env.AIDLC_ROOT) : process.cwd();
const harnessDir = path.join(root, ".harness");
const statePath = path.join(harnessDir, "state", "state.json");
const projectPath = path.join(harnessDir, "project.json");
const legacyGraphPath = path.join(harnessDir, "stage-graph.json");
const humanTurnPath = path.join(harnessDir, "state", "human-turn.json");
const profiles = new Set(["greenfield", "brownfield"]);
const normalizeProfile = (profile) => profile === "brownfield-maintenance" ? "brownfield" : profile;

const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const now = () => new Date().toISOString();
const writeJsonAtomic = (file, value) => {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(temp, file);
};
const output = (value) => process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
const fail = (summary, rootCause, safeRetry, stopCondition, code = 1) => {
  output({
    status: "error",
    summary,
    next_actions: [safeRetry],
    artifacts: [],
    root_cause_hint: rootCause,
    safe_retry: safeRetry,
    stop_condition: stopCondition
  });
  process.exit(code);
};

const graphPathFor = (profile) => {
  const profileGraph = path.join(harnessDir, "profiles", profile, "stage-graph.json");
  if (fs.existsSync(profileGraph)) return profileGraph;
  if (profile === "greenfield" && fs.existsSync(legacyGraphPath)) return legacyGraphPath;
  return profileGraph;
};
const configuredProfile = () => {
  if (!fs.existsSync(projectPath)) return "greenfield";
  return normalizeProfile(readJson(projectPath).project?.lifecycle_scope || "greenfield");
};
const load = (profileOverride = null) => {
  if (!fs.existsSync(statePath)) {
    fail("Harness files are missing", "state.json is absent", "Restore the harness files and run validate", "Stop until state exists");
  }
  const state = readJson(statePath);
  const profile = normalizeProfile(profileOverride || state.lifecycle_scope || configuredProfile());
  const graphPath = graphPathFor(profile);
  if (!profiles.has(profile) || !fs.existsSync(graphPath)) {
    fail("Harness profile is invalid", `No stage graph for ${profile}`, "Select greenfield or brownfield and restore its stage graph", "Stop until the profile is valid");
  }
  return { state, graph: readJson(graphPath), profile, graphPath };
};

const validate = () => {
  const required = [
    ".agents/rules/aidlc-core.md",
    ".agents/hooks.json",
    ".agents/workflows/aidlc.md",
    ".agents/workflows/aidlc-baseline.md",
    ".agents/workflows/aidlc-change.md",
    ".agents/workflows/aidlc-spec.md",
    ".agents/workflows/aidlc-ui-design.md",
    ".agents/skills/aidlc/SKILL.md",
    ".agents/skills/aidlc-baseline/SKILL.md",
    ".agents/skills/aidlc-change/SKILL.md",
    ".agents/skills/aidlc-spec/SKILL.md",
    ".agents/skills/aidlc-ui-design/SKILL.md",
    ".agents/agents/aidlc-developer.md",
    ".agents/agents/aidlc-frontend-designer.md",
    ".agents/rules/aidlc-brownfield.md",
    ".harness/project.json",
    ".harness/stage-graph.json",
    ".harness/profiles/brownfield/stage-graph.json",
    ".harness/state/state.json",
    ".harness/protocols/core.md",
    ".harness/protocols/source-authority.md",
    "project/brief.md",
    "project/specification-analysis.md",
    "project/ui-design.md",
    "project/ui-design-delta.md",
    "project/evidence/visual-verification.md"
  ];
  const missing = required.filter((file) => !fs.existsSync(path.join(root, file)));
  if (missing.length) fail("Harness validation failed", `Missing: ${missing.join(", ")}`, "Restore missing files", "Stop until required files exist");
  const hooks = readJson(path.join(root, ".agents", "hooks.json"));
  if (!hooks || typeof hooks !== "object" || Array.isArray(hooks)) {
    fail("Hooks configuration is invalid", ".agents/hooks.json must contain an object", "Restore hooks.json", "Stop until hooks are valid");
  }
  const state = readJson(statePath);
  for (const profile of profiles) {
    const graphPath = graphPathFor(profile);
    const graph = readJson(graphPath);
    if (!Array.isArray(graph.stages) || graph.stages.length === 0) fail("Stage graph is empty", `No stages are defined for ${profile}`, "Restore the profile stage graph", "Stop until at least one stage exists");
    const ids = graph.stages.map((stage) => stage.id);
    if (new Set(ids).size !== ids.length) fail("Stage IDs are not unique", `Duplicate stage id in ${profile}`, "Rename duplicate stages", "Stop until IDs are unique");
    for (const stage of graph.stages) {
      for (const key of ["id", "phase", "lead", "mode", "mandatory", "requires", "consumes", "produces", "gate", "done_when"]) {
        if (!(key in stage)) fail("Stage graph is invalid", `${profile}/${stage.id || "unknown"} lacks ${key}`, "Add the missing field", "Stop until every stage satisfies the contract");
      }
      for (const dependency of stage.requires) {
        if (!ids.includes(dependency)) fail("Stage dependency is invalid", `${profile}/${stage.id} requires unknown ${dependency}`, "Fix the dependency", "Stop until every dependency resolves");
      }
    }
  }
  if (!state.schema_version || !state.status) fail("State is invalid", "Required state fields are absent", "Restore state.json", "Stop until state is valid");
  output({ status: "success", summary: "Harness validation passed", next_actions: [], artifacts: required });
};

const initialize = (intentId, requestedProfile) => {
  if (!/^[a-z0-9][a-z0-9-]{2,63}$/.test(intentId || "")) {
    fail("Invalid intent ID", "Use 3-64 lowercase letters, digits, or hyphens", "Retry init with a kebab-case ID", "Stop until the ID is valid");
  }
  const profile = normalizeProfile(requestedProfile || configuredProfile());
  if (!profiles.has(profile)) {
    fail("Invalid lifecycle profile", profile, "Use greenfield or brownfield", "Stop until the profile is valid");
  }
  const { state, graph } = load(profile);
  if (!["uninitialized", "complete"].includes(state.status)) {
    fail("An active intent already exists", `Current status is ${state.status}`, "Use status or resume the active intent", "Stop unless the active intent is explicitly completed");
  }
  const stageSelection = {};
  const stageStatus = {};
  for (const stage of graph.stages) {
    stageSelection[stage.id] = stage.mandatory ? "execute" : "undecided";
    stageStatus[stage.id] = "pending";
  }
  const projectConfig = readJson(projectPath);
  projectConfig.project.lifecycle_scope = profile;
  if (profile === "brownfield" && projectConfig.project.baseline_status === "approved") {
    stageStatus.baseline = "completed";
  }
  writeJsonAtomic(projectPath, projectConfig);
  const next = {
    ...state,
    intent_id: intentId,
    lifecycle_scope: profile,
    status: "active",
    current_stage: null,
    current_unit: null,
    awaiting: null,
    stage_selection: stageSelection,
    stage_status: stageStatus,
    approved_gates: [],
    last_evidence: null,
    parked_reason: null,
    updated_at: now()
  };
  writeJsonAtomic(statePath, next);
  output({ status: "success", summary: `Initialized ${intentId} with ${profile}`, next_actions: ["Run next"], artifacts: [path.relative(root, statePath), path.relative(root, graphPathFor(profile))] });
};

const stageComplete = (state, id) => ["completed", "skipped"].includes(state.stage_status[id]);
const nextDirective = () => {
  const { state, graph } = load();
  if (state.status === "uninitialized") fail("Harness is not initialized", "No active intent", "Run init <intent-id>", "Stop until initialization");
  if (state.status === "parked") fail("Workflow is parked", state.parked_reason || "No reason recorded", "Resolve the blocker then run resume", "Stop while the blocker remains");
  if (state.awaiting) {
    output({ status: "warning", summary: `Awaiting human approval for ${state.awaiting.stage}`, next_actions: ["Ask the user to approve or request changes"], artifacts: state.awaiting.artifacts || [] });
    return;
  }
  for (const stage of graph.stages) {
    if (stageComplete(state, stage.id)) continue;
    const selection = state.stage_selection[stage.id];
    if (selection === "undecided") {
      output({ status: "warning", summary: `Selection required for optional stage ${stage.id}`, next_actions: [`Run select ${stage.id} execute|skip <reason>`], artifacts: [], stage });
      return;
    }
    if (selection === "skip") continue;
    const unresolved = stage.requires.filter((id) => !stageComplete(state, id));
    if (unresolved.length) {
      fail("Stage prerequisites are incomplete", `${stage.id} waits for ${unresolved.join(", ")}`, "Complete or explicitly skip prerequisites", "Stop until dependencies resolve");
    }
    state.current_stage = stage.id;
    state.stage_status[stage.id] = "in_progress";
    state.updated_at = now();
    writeJsonAtomic(statePath, state);
    output({ status: "success", summary: `Execute stage ${stage.id}`, next_actions: ["Load the declared agent and inputs", "Satisfy every done_when condition", stage.gate === "human" ? `Report ${stage.id} awaiting-approval` : `Report ${stage.id} completed`], artifacts: stage.consumes, stage });
    return;
  }
  state.status = "complete";
  state.current_stage = null;
  state.updated_at = now();
  writeJsonAtomic(statePath, state);
  output({ status: "success", summary: "Workflow complete", next_actions: [], artifacts: [] });
};

const select = (stageId, decision, reasonParts) => {
  const reason = reasonParts.join(" ").trim();
  const { state, graph } = load();
  const stage = graph.stages.find((item) => item.id === stageId);
  if (!stage || stage.mandatory) fail("Stage cannot be selected", "Stage is unknown or mandatory", "Select a known optional stage", "Stop until selection is valid");
  if (!['execute', 'skip'].includes(decision) || !reason) fail("Selection is incomplete", "Decision or reason is missing", "Use select <stage> execute|skip <reason>", "Stop until a reason is recorded");
  state.stage_selection[stageId] = decision;
  if (decision === "skip") state.stage_status[stageId] = "skipped";
  state.updated_at = now();
  writeJsonAtomic(statePath, state);
  output({ status: "success", summary: `${stageId} selected: ${decision}`, next_actions: ["Run next"], artifacts: [path.relative(root, statePath)], reason });
};

const report = (stageId, result, artifactArgs) => {
  const { state, graph } = load();
  const stage = graph.stages.find((item) => item.id === stageId);
  if (!stage || state.current_stage !== stageId) fail("Report rejected", "Stage is not current", "Run status and report the current stage", "Stop until stage identity matches");
  const artifacts = artifactArgs.filter(Boolean);
  if (result === "awaiting-approval") {
    if (stage.gate !== "human") fail("Gate report rejected", "Stage has no human gate", "Report completed instead", "Stop until result matches stage contract");
    state.stage_status[stageId] = "awaiting_approval";
    state.awaiting = { stage: stageId, opened_at: now(), artifacts };
  } else if (result === "completed") {
    if (stage.gate === "human") fail("Completion report rejected", "Human approval is required", "Report awaiting-approval", "Stop until a real approval is recorded");
    state.stage_status[stageId] = "completed";
    state.current_stage = null;
    state.last_evidence = artifacts;
  } else if (result === "failed") {
    state.stage_status[stageId] = "failed";
    state.status = "parked";
    state.parked_reason = artifactArgs.join(" ") || `${stageId} failed`;
  } else {
    fail("Unknown report result", result || "missing result", "Use awaiting-approval, completed, or failed", "Stop until result is valid");
  }
  state.updated_at = now();
  writeJsonAtomic(statePath, state);
  if (result === "failed") {
    output({
      status: "error",
      summary: `${stageId}: failed`,
      next_actions: ["Inspect the recorded failure, resolve its root cause, then run resume"],
      artifacts,
      root_cause_hint: state.parked_reason,
      safe_retry: "Resume only after the blocker is resolved and the retry hypothesis changes",
      stop_condition: "Keep the workflow parked while the failure remains"
    });
    return;
  }
  output({ status: "success", summary: `${stageId}: ${result}`, next_actions: result === "awaiting-approval" ? ["Wait for a new human turn"] : ["Run next"], artifacts });
};

const resolveGate = (decision, feedbackParts) => {
  const { state } = load();
  let completedBaselineOnboarding = false;
  if (!state.awaiting) fail("No approval gate is open", "State has no awaiting gate", "Run status", "Stop until a gate is open");
  if (!fs.existsSync(humanTurnPath)) fail("Approval rejected", "No recorded human turn", "Ask the user to approve or request changes", "The agent must not self-approve");
  const turn = readJson(humanTurnPath);
  if (!turn.recorded_at || new Date(turn.recorded_at) <= new Date(state.awaiting.opened_at)) {
    fail("Approval rejected", "No human turn occurred after the gate opened", "Wait for a new user response", "The agent must not self-approve");
  }
  const stageId = state.awaiting.stage;
  if (decision === "approve") {
    if (turn.decision !== "approve") {
      fail("Approval rejected", "The latest human prompt was not an explicit approval", "Ask the user to reply with Approve, Approved, Yes, Phê duyệt, Đồng ý, or Chấp thuận", "The agent must not reinterpret feedback or silence as approval");
    }
    state.stage_status[stageId] = "completed";
    state.approved_gates.push({ stage: stageId, approved_at: now(), human_turn_at: turn.recorded_at, prompt_sha256: turn.prompt_sha256 || null });
    state.current_stage = null;
    state.last_evidence = state.awaiting.artifacts || [];
    state.awaiting = null;
    if (stageId === "baseline" && normalizeProfile(state.lifecycle_scope) === "brownfield") {
      const projectConfig = readJson(projectPath);
      projectConfig.project.baseline_status = "approved";
      projectConfig.project.baseline_approved_at = now();
      writeJsonAtomic(projectPath, projectConfig);
      state.status = "complete";
      completedBaselineOnboarding = true;
    }
  } else if (decision === "reject") {
    const feedback = feedbackParts.join(" ").trim();
    if (!feedback) fail("Rejection requires feedback", "No revision guidance supplied", "Use reject <feedback>", "Stop until feedback exists");
    state.stage_status[stageId] = "in_progress";
    state.awaiting = null;
  } else {
    fail("Unknown gate decision", decision || "missing", "Use approve or reject <feedback>", "Stop until decision is valid");
  }
  state.updated_at = now();
  writeJsonAtomic(statePath, state);
  const nextAction = decision !== "approve"
    ? "Revise the stage artifacts"
    : completedBaselineOnboarding
      ? "Initialize a Brownfield change intent, then run /aidlc-change"
      : "Run next";
  output({ status: "success", summary: `${stageId}: ${decision}`, next_actions: [nextAction], artifacts: [] });
};

const park = (reasonParts) => {
  const reason = reasonParts.join(" ").trim();
  if (!reason) fail("Park reason required", "No reason supplied", "Use park <reason>", "Stop until the blocker is described");
  const { state } = load();
  state.status = "parked";
  state.parked_reason = reason;
  state.updated_at = now();
  writeJsonAtomic(statePath, state);
  output({ status: "warning", summary: "Workflow parked", next_actions: ["Resolve the blocker then run resume"], artifacts: [path.relative(root, statePath)] });
};

const resume = () => {
  const { state } = load();
  if (state.status !== "parked") fail("Workflow is not parked", `Status is ${state.status}`, "Run status or next", "Stop until resume is applicable");
  state.status = "active";
  state.parked_reason = null;
  state.updated_at = now();
  writeJsonAtomic(statePath, state);
  output({ status: "success", summary: "Workflow resumed", next_actions: ["Run next"], artifacts: [path.relative(root, statePath)] });
};

const status = () => {
  const { state } = load();
  output({ status: "success", summary: `${state.status}${state.current_stage ? ` at ${state.current_stage}` : ""}`, next_actions: state.status === "uninitialized" ? ["Run init <intent-id>"] : state.status === "parked" ? ["Resolve blocker and run resume"] : ["Run next"], artifacts: [path.relative(root, statePath)], state });
};

const [command, ...args] = process.argv.slice(2);
switch (command) {
  case "validate": validate(); break;
  case "init": initialize(args[0], args[1]); break;
  case "status": status(); break;
  case "next": nextDirective(); break;
  case "select": select(args[0], args[1], args.slice(2)); break;
  case "report": report(args[0], args[1], args.slice(2)); break;
  case "approve": resolveGate("approve", []); break;
  case "reject": resolveGate("reject", args); break;
  case "park": park(args); break;
  case "resume": resume(); break;
  default: fail("Unknown command", command || "missing command", "Use validate, init, status, next, select, report, approve, reject, park, or resume", "Stop until a valid command is used");
}
