# ADR-0011: Dồn lịch (compaction) sau khi tái lập lịch sự cố

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 02/10/2026 |
| Người quyết định | Nhóm dự án (chờ chốt ở review T-058) |
| Liên quan | ADC-004, FR 08 – FR 09, ADR-0004, T-033, T-058 |

## Bối cảnh

Thuật toán sự cố (T-033, ADR-0004) chỉ dời các đơn chồng lấn khung dừng; mọi đơn khác giữ nguyên slot. Khi đơn bị
ảnh hưởng chuyển đi chỗ khác, khe nó để lại bị bỏ trống dù đơn phía sau đã sẵn sàng. Ví dụ demo 03/10: Line A dừng
09:00–12:00, đơn ECFE2C (A 07:00–13:30) sang 04/10 → Line A rảnh 12:00–13:30 trong khi đơn CD1783 (sẵn hàng từ 07:00)
vẫn chờ tới 13:30. Yêu cầu: phương án sau sự cố phải tận dụng line tối đa, không để line nghỉ khi có đơn làm được.

## Các phương án

1. **Giữ nguyên (chỉ dời đơn bị ảnh hưởng)** — ít thay đổi nhất với khách; nhưng để line nghỉ, trái mục tiêu tận
   dụng line còn lại của ADC-004.
2. **Xếp lại toàn bộ đơn chưa bắt đầu từ đầu** (greedy BR-05 trên mọi đơn) — line kín nhất; nhưng đơn không liên quan
   có thể bị đẩy muộn hơn lịch đã hẹn (đơn ưu tiên cao chiếm chỗ), sinh SLA_RISK mới chỉ vì tái lập lịch.
3. **Dồn trái (left-shift compaction) sau bước tái lập lịch** — mỗi đơn chưa bắt đầu được xếp lại sớm nhất có thể,
   **chỉ nhận khi xong sớm hơn hẳn** lịch hiện tại; lặp tới khi không đổi. Lấp mọi khe lấp được mà không đơn nào xong
   muộn hơn; vẫn không tối ưu toàn cục (greedy).
4. **Solver (OR-Tools / MILP)** — tối ưu toàn cục; ngoài danh sách thư viện (ADR-0002), khó giải thích, quá sức MVP.

## Quyết định

Chọn **3**. Sau `reschedule` (bước 4–6), `compact` lặp theo thứ tự BR-05 (VIP → Khẩn → Thường, rồi giờ trả):

- Ứng viên: đơn vừa dời + đơn không bị ảnh hưởng ở trạng thái SCHEDULED / LINE_INCIDENT, slot bắt đầu ≥ hiện tại
  (cùng tập "chưa bắt đầu" với priority override). Đơn đang chạy, chờ / đã nhận hàng, hoặc thuộc đề xuất đang chờ
  duyệt giữ nguyên.
- Mỗi ứng viên được xếp lại bằng chính luật earliest feasible (khe trống, khung dừng, giờ hàng đến, ca làm). Chỉ nhận
  khi giờ xong mới **sớm hơn** giờ xong hiện tại; hòa giữ nguyên (không đổi line vô ích).
- Đơn không bị ảnh hưởng được kéo sớm → `outcome = PULLED_FORWARD`, `change_type = LINE_ASSIGNMENT` (không xong muộn
  hơn, không cần duyệt riêng), giữ trạng thái (không chuyển LINE_INCIDENT). Phương án vẫn chờ duyệt cả gói (T-033).

## Hệ quả

- ✅ Không đơn nào xong muộn hơn so với chỉ dời đơn bị ảnh hưởng; khe trống do sự cố được lấp nếu có đơn vừa.
- ✅ Vẫn deterministic, giải thích được từng dòng ("kéo sớm lấp khe trống").
- ⚠️ Phương án đổi nhiều đơn hơn (cả đơn không bị ảnh hưởng) → người duyệt xem nhiều dòng hơn; khách có đơn xong sớm
  hơn hẹn (không phải thông báo trễ).
- ⚠️ Vẫn greedy: không đổi chỗ 2 đơn để vừa khít hơn; khe ngắn hơn mọi đơn còn lại vẫn trống.
- 🔁 Việc tiếp theo: chốt với đối tác việc kéo sớm đơn đã hẹn có cần báo khách không; cân nhắc áp dụng compaction cho
  cả lịch thường (ngoài sự cố) nếu KPI (ADC-007) cho thấy line nghỉ nhiều.
