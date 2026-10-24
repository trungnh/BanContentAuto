# Frontend Design end-to-end

UI Design là optional stage nhưng phải chạy trước Plan khi intent thay đổi giao diện
web/mobile, user flow, navigation, responsive, accessibility hoặc design system.

## Greenfield

```text
/aidlc-init merchant-dashboard greenfield
/aidlc
```

Sau khi Discover và Requirements được duyệt, conductor hỏi chọn `ui-design`.
Chọn execute với lý do cụ thể, chạy tiếp `/aidlc`, rồi:

```text
/aidlc-ui-design docs/design-references
```

Reference path là tùy chọn, phải nằm trong repository. Agent tạo
`project/ui-design.md`, không viết frontend code, rồi dừng ở gate:

```text
Approve
```

Sau approval, Plan phải phân rã implementation theo screen/flow/state và giữ liên
kết tới visual acceptance criteria.

## Brownfield

```text
/aidlc-init feature-order-filter
/aidlc-change CR-456
```

Chọn `ui-design-delta` khi change ảnh hưởng UI. Sau khi stage trở thành current:

```text
/aidlc-ui-design docs/design-references/CR-456
```

`project/ui-design-delta.md` phải ghi rõ UI hiện tại, phần giữ nguyên, phần thay đổi
và màn hình ngoài scope. Không redesign toàn bộ hoặc thay design system nếu CR không
cho phép.

## Visual verification

Verify không được kết luận PASS chỉ từ build/unit test. Với UI stage đã approve,
`project/evidence/visual-verification.md` phải có evidence cho screen, state và
viewport đã cam kết, cùng accessibility result. Nếu thiếu environment, fixture,
route hoặc công cụ chụp/kiểm tra thì ghi BLOCKED, không giả lập PASS.

Human reviewer kiểm tra screenshot/evidence và phản hồi `Approve` hoặc
`Request Changes` tại Verify gate. Lifecycle approval không thay thế browser/tool
permission và cũng không tự deploy sản phẩm.
