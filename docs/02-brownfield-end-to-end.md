# AI-DLC Brownfield — Base Harness và hướng dẫn end-to-end

## 1. Mục tiêu

Profile `brownfield` dùng cho mọi project đã có trạng thái cần bảo vệ:
đã release, đang phát triển dở, được bàn giao, legacy, đang hiện đại hóa, hoặc có
consumer/data/operation hiện hữu. Profile dùng chung hooks, state, agents, evidence
và approval core với Greenfield nhưng thay điểm bắt đầu và cách route thay đổi.

```text
Brownfield outcome = approved AS-IS baseline + approved change delta
```

Proposal không được ghi thành hiện trạng trước khi thay đổi được chấp nhận.

## 2. Các trường hợp áp dụng

Không tạo workflow riêng cho từng công nghệ hay quy mô. Phân loại project để quyết
định độ sâu baseline, rồi phân loại từng change để chọn stage.

### 2.1 Theo trạng thái project

| Trường hợp | Nhu cầu onboarding | Điều chỉnh chính |
|---|---|---|
| Đã release, chỉ fix bug/CR | Bảo vệ behavior và compatibility | Baseline gọn, maintenance mặc định |
| Đã release, tiếp tục feature | Hiểu current contract và active modules | Requirements/design theo delta |
| Đang phát triển nhưng đã có code | Tách approved design khỏi code thử nghiệm | Ghi rõ phần ổn định/chưa ổn định |
| Project được bàn giao/inherited | Khôi phục tri thức và owner | Baseline sâu, UNKNOWN rõ |
| Legacy thiếu test/tài liệu | Characterize behavior an toàn | Baseline failures và characterization test |
| Monolith lớn | Giới hạn context và blast radius | Module map, active-area baseline, scoped rules |
| Multi-module/multi-repo | Quản lý boundary và version contract | Baseline từng repo + system contract index |
| Microservices/distributed | Contract, event và failure mode | Ownership, schema, observability, coexistence |
| Vendor/COTS/framework extension | Phân biệt owned và vendor code | Protected/generated paths, extension points |
| Modernization/migration | Vận hành song song cũ/mới | Architecture delta, migration, rollback |
| Fork/product line | Phân biệt upstream/local convention | Sync policy và divergence evidence |
| Regulated/sensitive system | Tăng gate và evidence | Security/data owner, deny production/secret paths |
| Hotfix/EOL system | Tối thiểu thay đổi và rollback | Maintenance path, không modernization kèm theo |

### 2.2 Theo quy mô và độ phức tạp

- **Nhỏ, một repository:** baseline toàn bộ nếu hợp lý.
- **Vừa, nhiều module:** inventory toàn bộ, khảo sát sâu active modules và boundary.
- **Lớn, nhiều repo/team:** baseline theo lớp: system index → repo/service baseline
  → change-local context. Không đưa toàn enterprise context vào always-on rules.
- **Rủi ro cao:** độ sâu do contract/data/security/operations quyết định, không do
  số dòng diff. Một config change nhỏ vẫn có thể là major evolution.

### 2.3 Theo chất lượng hiện trạng

- Build xanh, test tốt: commands và test suite là baseline evidence mạnh.
- Baseline đỏ: ghi exact failure; không quy lỗi cũ cho change mới hoặc báo PASS.
- Không có test: characterization cho behavior cần giữ, regression cho defect.
- Convention nhất quán: đưa phần confirmed vào project rules.
- Convention lẫn lộn: ghi inconsistency/legacy exception; owner quyết định hướng.
- Tài liệu khác code: ghi mâu thuẫn; agent không tự chọn âm thầm.

## 3. Phân loại từng thay đổi

### Maintenance

Localized bug/small compatible change, không ảnh hưởng đáng kể core business,
boundary, ownership, migration, trust, infrastructure hoặc nhiều team.

```text
Classify → Plan → Implement → Verify → Handoff
```

Thông thường skip exploration, requirements delta và architecture delta.

### Feature

Behavior mới trong ownership/architecture hiện tại; có thể cần compatible API,
schema, migration hoặc integration.

```text
Classify → Requirements Delta → [UI Design Delta] → [Design Delta] → Plan → Implement → Verify → Handoff
```

### Major evolution

Thay core business, boundary, ownership, breaking contract, consistency model,
platform, sensitive-data flow, nhiều system hoặc nhiều team.

```text
Classify → [Explore] → Requirements Delta → [UI Design Delta] → Architecture Delta
         → Plan → Incremental Implementation → Verify → Handoff
```

Explore chạy khi bài toán hoặc hướng giải pháp chưa rõ. Major classification không
cấp cho agent quyền quyết định business, cross-team architecture hay production.

## 4. Trigger tăng cấp

Đề xuất `major-evolution` khi có một trong các trigger:

- thay core business invariant hoặc domain ownership;
- breaking public API, event, schema, file hoặc configuration contract;
- đổi data ownership, destructive/large migration hoặc coexistence dài hạn;
- đổi transaction, consistency, concurrency hoặc idempotency model;
- thêm trust boundary, identity/authorization hoặc sensitive-data flow;
- đổi deployment topology, platform hoặc critical NFR/SLO;
- ảnh hưởng nhiều system, repository, team hoặc cần authority ngoài team.

Đề xuất ít nhất `feature` khi có behavior mới, nhiều acceptance flow, compatible
contract/schema, external integration hoặc ambiguity cần requirement delta.

Human xác nhận classification. Agent không tự downgrade để né stage hoặc upgrade để
mở rộng scope.

## 5. Cài harness vào project hiện hữu

1. Tạo branch onboarding riêng.
2. Copy harness vào repository root; nếu đã có `.agents/`, merge từng file.
3. Không copy credential, transcript, production log/data hoặc local settings.
4. Xác nhận `aidlc-core` Always On và kiểm tra `/hooks`, `/permissions`.
5. Giữ terminal/external/destructive action ở Ask hoặc Deny.
6. Điền tối thiểu `project/brief.md`: profile, repository/system identity, lý do
   onboarding, maintenance scope, constraints, prohibited data/actions và risks.
7. Chạy:

```bash
node .agents/scripts/aidlc.mjs validate
node .agents/scripts/smoke-test.mjs
node .agents/scripts/brownfield-smoke-test.mjs
```

## 6. Onboarding và baseline lần đầu

```text
/aidlc-init <onboarding-intent-id> brownfield
/aidlc-baseline
```

`<onboarding-intent-id>` là tên lifecycle intent, không bắt buộc chứa từ
`baseline`. ID chỉ cần dài 3–64 ký tự, bắt đầu bằng chữ thường hoặc số, và chỉ dùng
chữ thường, số hoặc dấu gạch ngang. Ví dụ:

```text
/aidlc-init payment-service-onboarding brownfield
/aidlc-init analyze-existing-system brownfield
/aidlc-init baseline-payment-service brownfield
```

Tên có `baseline` chỉ là convention dễ đọc, không phải cú pháp bắt buộc.

Agent inventory trước, rồi sample có chủ đích. Baseline bao phủ:

- tech stack/version và build/dependency authority;
- modules, ownership, dependency direction và entry points;
- source/test/config/migration/generated/protected paths;
- public API/event/schema/data/config/operations contracts;
- bootstrap, fast test, full verify, lint/static/security commands;
- security, data, production và external boundaries;
- baseline failures, legacy exceptions và unknowns.

Mỗi kết luận là `CONFIRMED`, `INFERRED`, `INCONSISTENT` hoặc `UNKNOWN`. Chỉ
`CONFIRMED` trở thành mandatory rule. Agent trình baseline plan trước khi ghi và
mở human gate sau validation. Khi human approve, state utility ghi baseline status
durable và kết thúc intent onboarding. Đây chưa phải intent thực hiện bug/CR;
intent change tiếp theo tự bỏ qua baseline.

Re-baseline khi có restructuring lớn, baseline drift có evidence, hoặc owner yêu
cầu; không chạy lại toàn bộ cho mỗi ticket.

## 7. Quy tắc tương tác chung

Mỗi lần `/aidlc` xử lý directive hiện tại và trả `next_actions`. Không nhập một
chuỗi command cố định mà bỏ qua output. Quy tắc sử dụng:

1. Khi agent báo `awaiting-approval`, đọc artifact rồi trả lời một lượt riêng:

   ```text
   Approve
   ```

   hoặc:

   ```text
   Request Changes: <nội dung cần sửa>
   ```

2. Khi output nói `Run next` hoặc `Run /aidlc`, nhập:

   ```text
   /aidlc
   ```

3. Khi current stage là `implement` và work plan có nhiều unit, dùng lần lượt:

   ```text
   /aidlc-implement UNIT-001
   /aidlc-implement UNIT-002
   ```

   Chỉ chạy unit đã được duyệt. Sau khi mọi unit hoàn tất, dùng `/aidlc` để chuyển
   sang verify.

4. Khi current stage là `verify`, có thể dùng:

   ```text
   /aidlc-verify
   ```

   hoặc để conductor thực hiện bằng `/aidlc`. Không approve nếu evidence còn FAIL,
   BLOCKED hoặc required check chưa chạy.

5. Có thể kiểm tra bất kỳ lúc nào mà không đổi state:

   ```text
   /aidlc-status
   ```

## 8. Walkthrough fix bug

Ví dụ `BUG-123`: khi nhập số tiền có phần thập phân, API trả sai error code. Baseline
project đã được duyệt.

### Bước 1 — Khởi tạo change intent

```text
/aidlc-init bug-123
```

Expected: profile lấy từ `.harness/project.json`, baseline được skip và next stage
là `classify`. Nếu agent trả lại `baseline`, dừng và kiểm tra baseline status/profile.

### Bước 2 — Cung cấp bug context và yêu cầu classify

Không nên chỉ gửi ID nếu harness không có Jira integration. Gửi đủ evidence đang có:

```text
/aidlc-change BUG-123

Loại yêu cầu: fix bug.
Hiện tượng: POST /payments với amount có phần thập phân trả INTERNAL_ERROR.
Mong đợi: trả validation error theo error contract hiện tại.
Cách tái hiện: dùng request fixture tests/fixtures/payment-decimal.json.
Phạm vi mong muốn: payment validation; không đổi public response schema.
Non-goals: không refactor payment module, không đổi dependency.
Evidence liên quan: <ticket/spec/log đã redaction hoặc file path>.

Hãy đọc baseline và source liên quan, xác định current behavior/root-cause area,
đề xuất classification cùng optional stages. Chỉ phân tích; chưa sửa code.
```

Agent phải cập nhật `project/change.md` và trình classify gate, thường đề xuất:

```text
class: maintenance
explore: skip
requirements-delta: skip
design-delta: skip
```

Review current/expected behavior, scope, trigger và evidence. Nếu đúng:

```text
Approve
```

Nếu agent chưa đủ evidence hoặc phân loại sai:

```text
Request Changes: chưa có evidence xác nhận public schema không đổi; hãy inspect
error contract hiện tại và cập nhật impact triggers trước khi classify lại.
```

### Bước 3 — Đi tới plan gate

```text
/aidlc
```

Lặp `/aidlc` theo `next_actions` để conductor ghi quyết định skip có reason và đi
tới `plan`. Với bug maintenance, plan tối thiểu phải có:

- cách tái hiện hoặc lý do không tái hiện được;
- root-cause hypothesis và file scope;
- regression test thất bại trước fix khi practical;
- minimal code change;
- targeted test và full verification command;
- baseline failure hiện hữu;
- done condition và out-of-scope.

Agent trình `project/work-plan.md` và chờ approval. Nếu đúng:

```text
Approve
```

### Bước 4 — Implement approved unit

```text
/aidlc
```

Nếu agent yêu cầu unit cụ thể:

```text
/aidlc-implement UNIT-001
```

Agent phải tạo regression test, thực hiện minimal fix và ghi actual command/result
vào `project/evidence/unit-UNIT-001.md`. Nếu test không thể viết trước fix, evidence
phải giải thích lý do và deterministic alternative; không được âm thầm bỏ test.

Sau khi tất cả unit hoàn tất:

```text
/aidlc
```

### Bước 5 — Verify và handoff

Khi `/aidlc-status` cho biết current stage là `verify`:

```text
/aidlc-verify
```

Review `project/evidence/verification.md` và `project/traceability.md`. Chỉ khi PASS:

```text
Approve
```

Sau đó:

```text
/aidlc
```

Agent tạo `project/evidence/handoff.md`. Chạy `/aidlc` lần nữa nếu `next_actions`
yêu cầu để state chuyển `complete`. Release/deploy không nằm trong change workflow
này trừ khi project đã cấu hình một quy trình riêng có authority phù hợp.

## 9. Walkthrough làm feature/CR

Ví dụ `CR-456`: bổ sung hạn mức giao dịch theo phân khúc khách hàng trong payment
module hiện tại.

### Bước 1 — Khởi tạo feature intent

```text
/aidlc-init feature-customer-limit
```

### Bước 2 — Cung cấp requirement context

```text
/aidlc-change CR-456

Mục tiêu: bổ sung hạn mức giao dịch theo customer segment.
Current behavior: mọi customer dùng cùng một daily limit.
Expected behavior:
- STANDARD dùng limit hiện hành;
- PRIORITY dùng limit cấu hình riêng;
- segment không xác định phải fail theo error contract hiện tại.
Acceptance criteria: <liệt kê AC hoặc đường dẫn spec>.
Phạm vi: payment limit evaluation và cấu hình liên quan.
Non-goals: không thay customer segmentation source; không đổi authentication.
Compatibility: existing STANDARD behavior phải được giữ nguyên.
Known constraints: không đọc production data; migration/config phải backward-compatible.

Hãy đọc baseline và source liên quan, lập impact map, đề xuất classification và
các stage cần execute. Chỉ phân tích; chưa sửa code.
```

Agent thường đề xuất `feature`. Review trigger:

- `requirements-delta`: thường execute;
- `design-delta`: execute nếu có contract, schema, migration, integration,
  transaction, trust, NFR hoặc operations impact;
- `explore`: skip nếu mục tiêu/solution direction đã rõ.

Nếu đúng:

```text
Approve
```

### Bước 3 — Requirements delta

```text
/aidlc
```

Conductor chọn optional stages theo classification đã duyệt. Khi
`requirements-delta` chạy, agent tạo `project/requirements-delta.md` với:

- stable requirement IDs;
- behavior mới/thay đổi;
- observable acceptance criteria;
- behavior phải giữ;
- source/owner;
- compatibility và ambiguity.

Đọc artifact rồi:

```text
Approve
```

hoặc yêu cầu sửa cụ thể. Không approve requirement do agent tự suy diễn.

### Bước 4 — Architecture delta khi có trigger

Tiếp tục:

```text
/aidlc
```

Nếu không có design trigger, agent phải ghi reason và skip. Nếu có, agent tạo
`project/architecture-delta.md`, mô tả current → target, affected boundary,
contract/data, coexistence/migration, failure mode, security/operations, rollout và
rollback. Baseline AS-IS vẫn không bị ghi đè.

Review rồi:

```text
Approve
```

### Bước 5 — Plan, implement, verify

Tiếp tục `/aidlc` tới plan gate. Plan phải trace mỗi requirement delta sang unit và
test/evidence. Sau khi review:

```text
Approve
```

Thực hiện từng unit:

```text
/aidlc
/aidlc-implement UNIT-001
/aidlc-implement UNIT-002
```

Số unit lấy từ `project/work-plan.md`; không mặc định feature luôn có hai unit.
Sau khi hoàn tất:

```text
/aidlc
/aidlc-verify
```

Review verification/traceability. Nếu PASS:

```text
Approve
/aidlc
```

Handoff phải nêu behavior mới, preserved behavior, compatibility, checks, residual
risk và human-owned next action.

## 10. Feature lớn hoặc mở rộng core business

Không quay project về Greenfield. Giữ Brownfield và kích hoạt capability theo delta:

- exploration cho problem/solution direction;
- requirements delta cho behavior mới và preserved behavior;
- architecture delta cho current → target, coexistence và migration;
- security/operations review theo trigger;
- work decomposition và incremental verification.

Nếu classification là `major-evolution`, sau classify gate hãy dùng `/aidlc` để đi
qua `explore` khi cần, rồi requirements và architecture delta. Mỗi stage có artifact
và approval riêng; không dùng một approval chung cho toàn bộ thiết kế lớn.

Proposal nằm ở `project/change-exploration.md`, `requirements-delta.md` và
`architecture-delta.md`. Chỉ sau khi change được chấp nhận mới cập nhật baseline,
architecture, context và operations thành AS-IS mới qua một review riêng.

## 11. Definition of Done Brownfield

- baseline đã duyệt và change nằm trong coverage phù hợp;
- classification và optional stages có evidence, được human xác nhận;
- current, changed và preserved behavior rõ;
- diff là thay đổi nhỏ nhất trong approved scope;
- bug có reproduction/regression test khi practical;
- required checks chạy thật, lỗi baseline tách khỏi lỗi mới;
- compatibility/migration/security/operations evidence có khi triggered;
- traceability từ change/AC đến code và test;
- handoff nêu residual risk và human-owned next actions;
- không có production/external/destructive action hoặc self-approval ngoài quyền.

## 12. Khi nào dừng và escalate

- thiếu business/contract authority;
- chỉ có production data mới tái hiện được lỗi;
- secret hoặc dữ liệu nhạy cảm nằm ngoài approved boundary;
- migration/rollback không an toàn hoặc ownership không rõ;
- baseline failure làm verification không thể diễn giải;
- thay đổi cross-team chưa có owner/approval;
- requirement mâu thuẫn behavior/contract đang vận hành;
- retry đạt giới hạn mà giả thuyết root cause không thay đổi.

Park workflow với root cause, safe retry và stop condition; không bypass gate.

## 13. Artifact ownership

| Artifact | Ý nghĩa |
|---|---|
| `project/baseline.md` | AS-IS đã duyệt |
| `project/context.md`, `architecture.md`, `operations.md` | Project truth hiện hành |
| `project/change.md` | Intake và classification của intent hiện tại |
| `project/change-exploration.md` | Exploration có điều kiện |
| `project/requirements-delta.md` | Behavior delta |
| `project/architecture-delta.md` | Architecture/operations delta |
| `project/work-plan.md` | Approved units của change hiện tại |
| `project/evidence/` | Command/verification/handoff evidence thật |
| `.agents/rules/project-*.md` | Chỉ convention confirmed, project-specific |

Với nhiều change song song, không dùng chung một worktree/state. Tạo worktree hoặc
workspace copy riêng cho mỗi intent để tránh `project/change*.md` và state ghi đè.
