var fso = new ActiveXObject("Scripting.FileSystemObject");
var root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName));
var required = [
  ".agents\\rules\\aidlc-core.md",
  ".agents\\hooks.json",
  ".agents\\scripts\\aidlc.mjs",
  ".agents\\workflows\\aidlc.md",
  ".agents\\workflows\\aidlc-baseline.md",
  ".agents\\workflows\\aidlc-change.md",
  ".agents\\workflows\\aidlc-spec.md",
  ".agents\\workflows\\aidlc-ui-design.md",
  ".agents\\skills\\aidlc\\SKILL.md",
  ".agents\\skills\\aidlc-baseline\\SKILL.md",
  ".agents\\skills\\aidlc-change\\SKILL.md",
  ".agents\\skills\\aidlc-spec\\SKILL.md",
  ".agents\\skills\\aidlc-ui-design\\SKILL.md",
  ".agents\\agents\\aidlc-frontend-designer.md",
  ".agents\\agents\\aidlc-developer.md",
  ".agents\\rules\\aidlc-brownfield.md",
  ".harness\\project.json",
  ".harness\\stage-graph.json",
  ".harness\\profiles\\brownfield\\stage-graph.json",
  ".harness\\state\\state.json",
  ".harness\\protocols\\source-authority.md",
  "project\\brief.md",
  "project\\specification-analysis.md",
  "project\\ui-design.md",
  "project\\ui-design-delta.md",
  "project\\evidence\\visual-verification.md"
];
var jsonFiles = [
  ".agents\\hooks.json",
  ".harness\\project.json",
  ".harness\\stage-graph.json",
  ".harness\\profiles\\brownfield\\stage-graph.json",
  ".harness\\state\\state.json",
  ".harness\\contracts\\observation.schema.json"
];
var failed = false;

function full(relative) { return fso.BuildPath(root, relative); }
function read(file) {
  var stream = fso.OpenTextFile(file, 1, false, -1);
  var text = stream.ReadAll();
  stream.Close();
  return text;
}

for (var i = 0; i < required.length; i++) {
  if (!fso.FileExists(full(required[i]))) {
    WScript.Echo("MISSING " + required[i]);
    failed = true;
  }
}
for (var j = 0; j < jsonFiles.length; j++) {
  try {
    eval("(" + read(full(jsonFiles[j])) + ")");
  } catch (error) {
    WScript.Echo("INVALID JSON " + jsonFiles[j] + ": " + error.message);
    failed = true;
  }
}
if (failed) WScript.Quit(1);
WScript.Echo("Antigravity harness static validation passed.");
WScript.Quit(0);
