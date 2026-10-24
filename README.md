# AI-DLC Harness for Google Antigravity

Bộ harness triển khai AI-Driven Development Life Cycle trên Google Antigravity
2.0/CLI bằng workspace rules, slash-command workflows, on-demand skills, scoped
subagents, JSON hooks, deterministic state và human approval gates.

Hai profile dùng chung một core:

- `greenfield`: xây hệ thống mới từ intent đến release/operate;
- `brownfield`: baseline hệ thống hiện hữu rồi route từng thay đổi theo
  maintenance, feature hoặc major evolution.

## Cấu trúc

```text
.agents/
├── rules/          Always-on AI-DLC invariants
├── workflows/      Slash commands: /aidlc-*
├── skills/         On-demand workflow knowledge
├── agents/         Scoped specialist subagents
├── scripts/        Deterministic state và hook runtime
└── hooks.json      PreInvocation, PreToolUse, PostToolUse hooks
.harness/           Stage graph, protocols, contracts và state
project/            Durable artifacts và evidence
evals/              Harness behavior evaluation cases
scripts/            Repository-level validation utilities
```

## Bắt đầu

1. Copy toàn bộ nội dung harness vào workspace root.
2. Mở folder đó như một Antigravity Project.
3. Trong Customizations, xác nhận `.agents/rules/aidlc-core.md` và đặt rule thành
   **Always On**.
4. Kiểm tra JSON hooks bằng `/hooks`.
5. Giữ execution mode ở `default/request-review` trong lần sử dụng đầu tiên.
6. Điền `project/brief.md`; Greenfield có thể chạy `/aidlc-brainstorm` trước.
7. Chạy `/aidlc-init <intent-id> <profile>`, `/aidlc-status`, rồi `/aidlc`.
8. Với project hiện hữu, chạy baseline một lần rồi dùng `/aidlc-change` cho mỗi
   bug, CR, feature hoặc major evolution.

## Workflows

| Command | Mục đích |
|---|---|
| `/aidlc-brainstorm` | Khám phá ý tưởng trước lifecycle |
| `/aidlc-init <intent-id> [profile]` | Khởi tạo Greenfield hoặc Brownfield intent |
| `/aidlc-baseline` | Khảo sát và duyệt baseline project hiện hữu |
| `/aidlc-change` | Phân loại và thực hiện thay đổi Brownfield tương xứng rủi ro |
| `/aidlc-spec <path>` | Chuẩn hóa specification trong repository trước khi design/code |
| `/aidlc-ui-design [reference-path]` | Thiết kế UI/UX có approval gate trước frontend implementation |
| `/aidlc-status` | Xem state, không thay đổi workflow |
| `/aidlc` | Chạy hoặc tiếp tục stage hiện tại |
| `/aidlc-implement <UNIT-ID>` | Implement một approved work unit |
| `/aidlc-verify` | Independent verification |
| `/aidlc-release` | Release có approval và rollback controls |

## Validate

```bash
node .agents/scripts/aidlc.mjs validate
node .agents/scripts/smoke-test.mjs
node .agents/scripts/brownfield-smoke-test.mjs
```

## Security model

- Lifecycle approval và Antigravity tool permission là hai lớp độc lập.
- `risk-gate.mjs` yêu cầu review terminal commands và dùng `force_ask` cho một số
  command có external/destructive impact; project permissions vẫn cần được cấu
  hình theo environment thực tế.
- Không dùng `accept-edits`, broad allow rules hoặc unrestricted access để bypass
  human gates.
- Subagents chạy với `commandExecutionPolicy: sandbox` và tool list theo role.

Đọc [hướng dẫn chung](docs/01-huong-dan-su-dung.md),
[hướng dẫn Brownfield end-to-end](docs/02-brownfield-end-to-end.md), và
[hướng dẫn dùng Specification](docs/03-su-dung-specification-dau-vao.md), và
[Frontend Design end-to-end](docs/04-frontend-design-end-to-end.md) trước khi áp
dụng vào project thật.
