# Product Vision — ADC Irradiation Work Order Orchestrator (MFG 08)

> Nguồn: *ADC Irradiation Work Order Project Brief* và *PRD*.

| Trường | Giá trị |
|---|---|
| Dự án | ADC Irradiation Work Order — MFG 08 |
| Loại | Build phase concept — multi-agent orchestration với human approval |
| Thời lượng build | 6 tuần (6 sprint × 1 tuần, mốc M1–M8 — xem `docs/roadmap.md`) |
| Trạng thái | Draft |

## 1. Pitch một câu

Một **"control tower" multi-agent** cho dịch vụ chiếu xạ kiểu ADC: xếp lịch đơn hàng bình thường và xử lý sự cố line bằng phục hồi theo ưu tiên, cảnh báo rủi ro và thông điệp khách hàng **do con người phê duyệt**.

## 2. Vấn đề

Đơn hàng đến dưới dạng ticket gồm sản phẩm, số lượng, quy cách thùng, liều chiếu yêu cầu, mức ưu tiên và giờ trả mong muốn. Trong quy trình thủ công, kinh doanh hứa giờ trả với khách trong khi năng lực sản xuất và kho được kiểm tra riêng. Khi một line dừng, nhóm phải tự tìm đơn bị ảnh hưởng và dựng lại lịch.

Bốn rủi ro:

1. Trả hàng trễ cho khách
2. Sử dụng line kém hiệu quả
3. Đánh đổi ưu tiên sai
4. Nhận đơn mới khi hệ thống đã quá tải

## 3. Giải pháp & USP

Hệ thống đọc ticket, ước tính tải xử lý từ giả định cấu hình được, xếp lịch 2 line chiếu xạ và xử lý sự cố bằng tái lập lịch theo ưu tiên.

**USP:** khi Line A gặp sự cố → kiểm tra năng lực Line B → bảo vệ đơn ưu tiên cao → ngăn nhận đơn mới rủi ro → escalate các ca trả trễ cho kinh doanh.

## 4. Vì sao cần AI — và AI không làm gì

| AI làm | Luật deterministic làm |
|---|---|
| Hiểu ticket bán cấu trúc, hỏi lại khi thiếu (Order Agent) | Ước tính thời lượng (công thức cấu hình) |
| Suy luận trên trạng thái lịch, ưu tiên, sự cố, rủi ro | Tính lịch, tìm slot, kiểm tra chồng lấn |
| Điều phối giữa tiếp nhận, xếp lịch, rủi ro, escalation | Quyết định mức rủi ro OK/WARN/BLOCK |
| Giải thích vì sao đơn bị dời/hoãn/chặn bằng ngôn ngữ nghiệp vụ | Luật cần phê duyệt |
| Soạn nháp thông điệp escalation | — |

> Phép tính lịch phải deterministic để kế hoạch tái lập được. AI xử lý đầu vào lộn xộn và điều phối; luật và logic xếp lịch tạo ra kế hoạch.

## 5. Mục tiêu và Non-goals

| Goals | Non-goals |
|---|---|
| Xếp lịch work order chiếu xạ từ dữ liệu ticket | Điều khiển máy chiếu xạ hoặc chứng nhận an toàn chiếu xạ |
| Phục hồi khi Line A hoặc Line B gặp sự cố | Tính liều thật (dosimetry) hoặc giải phóng lô theo quy định |
| Bảo vệ đơn ưu tiên cao và khẩn | Thay thế ERP, WMS, MES, billing, tồn kho |
| Cảnh báo/chặn đơn mới rủi ro khi quá tải do sự cố | Huấn luyện ML trên dữ liệu sản xuất ADC (không có) |
| HITL cho quyết định ảnh hưởng khách | Tự động thay đổi cam kết với khách |

## 6. Phạm vi MVP

| In scope | Out of scope |
|---|---|
| Tiếp nhận ticket và trích xuất trường | Điều khiển trực tiếp máy chiếu xạ |
| Throughput mô phỏng từ số lượng, quy cách, nhóm mật độ, liều | Tính liều thật / giải phóng lô |
| Lịch Line A và Line B | Thay thế ERP, WMS, billing, kế toán |
| Xử lý sự cố và tái lập lịch theo ưu tiên | IoT telemetry thật hoặc huấn luyện ML production |
| Cảnh báo rủi ro, chặn đơn, escalation cho kinh doanh | Tự động đổi cam kết với khách khi chưa duyệt |

## 7. Định nghĩa thành công

- Ticket bình thường → work order đã xếp lịch **dưới 5 giây** trên dữ liệu demo.
- Sự cố Line A → phát hiện đơn bị ảnh hưởng và đề xuất phương án phục hồi trên Line B.
- Đơn ưu tiên cao được bảo vệ trước đơn thường.
- Đơn mới bị cảnh báo hoặc chặn khi việc nhận sẽ làm rủi ro SLA tệ hơn.
- Mọi thay đổi ảnh hưởng khách vào trạng thái chờ duyệt trước khi kích hoạt.

## 8. Metrics (demo target)

| Metric | Target |
|---|---|
| Ticket → lịch | < 5 giây |
| Thời gian đề xuất phục hồi sự cố | < 10 giây |
| Thay đổi ảnh hưởng khách không qua duyệt | 0 |
| Work order có lịch sử trạng thái | 100% |
| Đơn mới rủi ro được cảnh báo trong sự cố | 100% |
| Escalation được tạo cho ca trả trễ | 100% ca có rủi ro trễ |

## 9. Kịch bản demo

| Kịch bản | Hành vi mong đợi |
|---|---|
| Normal order | Ticket được parse, ước tính thời lượng, xếp lên line khả thi sớm nhất |
| Capacity conflict | Line A không vừa → Scheduler kiểm tra Line B và đề xuất phương án khác |
| Line A incident | Tìm đơn bị ảnh hưởng, đơn ưu tiên cao sang Line B, đơn ưu tiên thấp bị trễ được escalate |
| New order during incident | Cảnh báo hoặc chặn nếu không bảo vệ được giờ trả yêu cầu |
