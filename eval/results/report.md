# Evaluation Report — ADC Irradiation Work Order

> Báo cáo đánh giá chất lượng sản phẩm theo Metrics của PRD (`specs/product-vision.md` §8) và tiêu chí thành công trong từng đặc tả `tasks/ADC-*.md`.
> Mọi số liệu đo trên **seed dataset cố định** (`src/seed/`), reset trước mỗi lần đo.

---

## 1. Metrics PRD (demo target)

| Metric | Target | Actual | Status | Cách đo |
|--------|--------|--------|--------|---------|
| Ticket → lịch | < 5 giây | — | ⏳ | Thời gian từ lúc xác nhận ticket tới lúc có slot, ghi trong `audit_log` (ADC-003, ADC-007) |
| Thời gian đề xuất phục hồi sự cố | < 10 giây | — | ⏳ | Sự cố Line A 09:00–12:00 → plan version đề xuất (ADC-004) |
| Thay đổi ảnh hưởng khách không qua duyệt | 0 | — | ⏳ | Đếm plan version ACTIVE có `plan_changes.needs_approval` mà chưa có `approved_by` (ADC-006) |
| Work order có lịch sử trạng thái | 100% | — | ⏳ | Tỷ lệ work order có `state_history` đầy đủ từ DRAFT (ADC-006) |
| Đơn mới rủi ro được cảnh báo trong sự cố | 100% | — | ⏳ | Kịch bản 5 — đơn mới trong sự cố có `risk_checks` WARN/BLOCK (ADC-005) |
| Escalation được tạo cho ca trả trễ | 100% ca có rủi ro trễ | — | ⏳ | Mọi đơn SLA_RISK trễ có `escalations` (ADC-005) |

## 2. Chất lượng AI

| Chỉ số | Target (đề xuất, chốt với mentor) | Actual | Status | Nguồn |
|--------|--------|--------|--------|-------|
| Độ chính xác trích xuất — PDF văn bản số | ≥ 95% | — | ⏳ | `make eval-intake` → `eval/results/intake-extraction.md` (16 PDF, T-022) |
| Độ chính xác trích xuất — PDF scan | ≥ 85% | — | ⏳ | ≥ 5 bản scan |
| Phát hiện đúng trường thiếu | 100% | — | ⏳ | ADC-001 TC3 |
| Trang/vùng nguồn đúng | — | — | ⏳ | ADC-001 |
| PDF 1 trang → form kết quả | < 10 giây | — | ⏳ | ADC-001 |
| Câu giải thích của Scheduler Agent khớp số liệu | 100% qua validator | — | ⏳ | ADC-003, ADC-004 |
| Nháp thông điệp đạt checklist (không hứa sai giờ, không nhắc an toàn/liều) | 10/10 tình huống | — | ⏳ | ADC-005, chấm tay |

## 3. Lõi deterministic

| Chỉ số | Target | Actual | Status |
|--------|--------|--------|--------|
| Ví dụ chuẩn ADC-002 (120 thùng × 8 kg, 40×30×25 cm, gia vị, 10 kGy) | 180 phút | 180 phút | ✅ |
| Cùng input chạy 100 lần → cùng kết quả | 100% | 100% | ✅ |
| 20 lệnh ngẫu nhiên → không chồng lấn slot | 0 chồng lấn | 0 | ✅ |
| Kịch bản Line A incident giống nhau sau mỗi lần reset | 100% | — | ⏳ |
| Chế độ 1 line có số đơn trễ ≥ chế độ 2 line (seed) | Đúng | — | ⏳ |

## 4. Test Results

### Unit Tests
```
pytest tests/ -v
# Paste output here — kèm ngày chạy và commit
```

### Kịch bản demo (`docs/demo-scenarios.md`)

| # | Kịch bản | Kết quả | Ghi chú |
|---|---|---|---|
| 1 | Normal order | ⏳ | |
| 2 | Missing fields | ⏳ | |
| 3 | Capacity conflict | ⏳ | |
| 4 | Line A incident (USP) | ⏳ | |
| 5 | New order during incident | ⏳ | |
| 6 | KPI & 1 line vs 2 line | ⏳ | |

## 5. User Feedback (đối tác, mentor)

| Người dùng / vai trò | Feedback | Rating |
|------|----------|--------|
| [Đối tác — Kinh doanh] | [feedback] | [1-5] |
| [Đối tác — Điều phối] | [feedback] | [1-5] |

## 6. Demo Results

| | Demo 1 (W3 · M4) | Demo 2 (W5 · M6) |
|---|---|---|
| Ngày | [YYYY-MM-DD] | [YYYY-MM-DD] |
| Người tham gia | | |
| Feedback chung | | |
| Issues phát hiện | | |

## 7. Action Items

- [ ] [Cần cải thiện 1] — gắn `T-xxx` / `BUG-xxx`
- [ ] [Cần cải thiện 2]
