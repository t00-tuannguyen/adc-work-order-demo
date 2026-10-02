# ADR-0007: Cổng HITL tiếp nhận theo độ tin cậy OCR/trích xuất

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 26/09/2026 |
| Người quyết định | [Họ tên] |
| Liên quan | ADC-001, FR 01, FR 02, ADR-0001, ADR-0005 |

## Bối cảnh

Thiết kế cũ của ADC-001 bắt mọi ticket dừng ở form kết quả để Kinh doanh bấm "Tạo lệnh" (`POST /api/work-orders/{id}/submit`), kể cả khi PDF văn bản số trích xuất rõ ràng 100%. Việc xác nhận thủ công mọi ticket làm chậm luồng "ticket → lịch" và khiến người dùng quen tay bấm duyệt, giảm chú ý đúng vào các ticket thực sự đáng ngờ (bản scan mờ, giá trị suy luận).

## Các phương án

1. **Luôn HITL sau trích xuất** (hiện tại) — an toàn nhưng chậm, "mỏi duyệt".
2. **Không HITL, chỉ dựa validator** — nhanh nhưng số liệu OCR sai (nhầm 120 thùng / 120 kg) có thể lọt vào lịch.
3. **Cổng theo độ tin cậy, 3 mức** — code quyết định dựa trên độ tin cậy OCR từng vùng + nhãn nguồn:
   - **AUTO**: rõ ràng → tự chuyển FEASIBILITY_CHECK, không cần người xác nhận.
   - **WARN**: không rõ ràng → vẫn tự đi tiếp, tạo cảnh báo cho người xem lại.
   - **REVIEW**: tin cậy thấp → giữ DRAFT, người phải xác nhận trường bị gắn cờ rồi mới submit.

## Quyết định

Chọn **3**. Bước `assess` (thuần, `src/modules/intake/confidence.py`) chạy sau validator trong luồng tiếp nhận:

| Tín hiệu | Mức |
|---|---|
| Độ tin cậy OCR < `low_confidence_threshold` (0,8) hoặc nhãn `OCR_LOW` | REVIEW (`LOW_CONFIDENCE`) |
| Không chắc ranh giới ticket trong file nhiều ticket | REVIEW (`BOUNDARY_UNCERTAIN`) |
| `low` ≤ độ tin cậy < `warn_confidence_threshold` (0,9) | WARN (`AMBIGUOUS_OCR`) |
| Nhãn `INFERRED` (vd ưu tiên suy từ "gấp") | WARN (`INFERRED_VALUE`) |
| Nhãn `DEFAULT` | WARN (`DEFAULT_VALUE`) |
| File trùng sha256 | WARN (`POSSIBLE_DUPLICATE`) |
| Trường `MANUAL` (người đã nhập/xác nhận) | không gắn cờ |

- Có ≥ 1 cờ REVIEW → REVIEW; không có REVIEW nhưng có cờ → WARN; không cờ → AUTO.
- Thiếu/sai trường vẫn do validator xử lý như cũ (BR-01) và luôn dừng ở DRAFT, bất kể mức tin cậy.
- Độ tin cậy lấy từ OCR vùng nguồn, **do code gắn** vào từng trường; không dùng độ tin cậy LLM tự khai. Text layer / nhập tay → không có độ tin cậy → coi như chắc chắn.
- Ngưỡng cấu hình ở mục `ocr` của `src/config/throughput.yaml`.
- Cổng này chỉ thay bước **xác nhận dữ liệu đầu vào**. Cổng duyệt plan version (ADR-0005) giữ nguyên: đơn tự đi tiếp mà gây ảnh hưởng SLA vẫn vào PENDING_APPROVAL.

## Hệ quả

- ✅ Ticket rõ ràng đi thẳng tới lịch, không chờ người; người chỉ tập trung vào ticket đáng ngờ.
- ✅ Quyết định deterministic, tái lập, test được (không để LLM tự chấm điểm).
- ⚠️ Đơn WARN có thể đã được xếp lịch khi người phát hiện sai. Sửa trường sau khi đã có lịch → tạo plan version mới theo luật ADR-0005 (đổi giờ trả → cần duyệt).
- ⚠️ Chất lượng cổng phụ thuộc hiệu chỉnh ngưỡng; cần đo trên bộ PDF mẫu (T-022): tỷ lệ AUTO sai phải ≈ 0.
- 🔁 Việc tiếp theo: T-048 trả độ tin cậy theo vùng; T-019 gắn `confidence` vào từng trường; T-021 UI banner cảnh báo + hàng đợi "Cần xác nhận"; bảng `intake_warnings` + API xác nhận cảnh báo.
