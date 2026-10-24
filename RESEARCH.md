# Antigravity adapter research notes

Adapter này dựa trên tài liệu chính thức được kiểm tra ngày 2026-08-19:

- Rules và workflows: https://antigravity.google/docs/rules-workflows
- Agent Skills: https://antigravity.google/docs/skills
- Custom subagents: https://antigravity.google/docs/subagents
- JSON Hooks: https://antigravity.google/docs/hooks
- Permissions: https://antigravity.google/docs/permissions
- Projects: https://antigravity.google/docs/projects

Các quyết định chính:

- dùng `.agents/` là convention hiện hành, không dùng legacy `.agent/`;
- rules giữ invariant, workflows cung cấp slash commands, skills chứa hướng dẫn
  on-demand, agents định nghĩa scoped subagents;
- hooks dùng `PreInvocation`, `PreToolUse` và `PostToolUse` theo schema chính thức;
- lifecycle state vẫn do JavaScript deterministic utility sở hữu;
- human approval được ghi từ transcript ở `PreInvocation`, không tin vào lời tự
  khai của model;
- permissions và lifecycle gates là hai lớp tách biệt.
