# User Roles — Vai trò, phân quyền & luật phê duyệt

## 1. Vai trò

| Role (enum) | Tên | Việc chính |
|---|---|---|
| SALES | Kinh doanh / CSKH | Tải PDF, xác nhận ticket, xử lý escalation, liên hệ khách, duyệt thông điệp |
| PLANNER | Điều phối sản xuất / Trưởng ca | Xếp & sửa lịch, khai báo sự cố, chuyển trạng thái vận hành, đề xuất plan |
| OPS_MANAGER | Quản lý vận hành | Duyệt plan version, override BLOCK, xem KPI |
| ADMIN | Quản trị hệ thống | Duyệt tài khoản mới, cấp/thu hồi vai trò |
| — | Mentor / giám khảo | Xem truy vết & dashboard khi demo |

User mới đăng nhập Google ở trạng thái `PENDING` — không truy cập dữ liệu cho tới khi ADMIN cấp vai trò.

## 2. Ma trận quyền

| Hành động | SALES | PLANNER | OPS_MANAGER | ADMIN |
|---|:-:|:-:|:-:|:-:|
| Tải PDF / tạo work order | ✅ | ❌ | ❌ | ❌ |
| Xem Kanban, lịch, KPI | ✅ | ✅ | ✅ | ✅ |
| Xếp / sửa lịch (đơn mới được hệ thống tự xếp khi tạo ticket) | ❌ | ✅ | ❌ | ❌ |
| Chuyển trạng thái vận hành thủ công | ❌ | ✅ | ❌ | ❌ |
| Khai báo sự cố | ❌ | ✅ | ❌ | ❌ |
| Duyệt / từ chối plan version | ✅ | ❌ | ✅ | ❌ |
| Override đơn BLOCK (kèm lý do) | ❌ | ❌ | ✅ | ❌ |
| Duyệt thông điệp escalation | ✅ | ❌ | ✅ | ❌ |
| Quản lý người dùng & vai trò | ❌ | ❌ | ❌ | ✅ |

- Người đề xuất không tự duyệt plan của mình (Nên có).
- Admin cuối cùng không tự hạ quyền hoặc vô hiệu hóa chính mình.
- Chỉnh file cấu hình throughput: chỉ nhóm phát triển, qua repo.
- Endpoint reset demo chỉ bật ở môi trường demo/staging.

## 3. Human-in-the-loop — ranh giới

| AI được đề xuất | Con người phải duyệt |
|---|---|
| Trích xuất trường ticket, xác định thông tin thiếu | Giờ trả mới hoặc thay đổi giờ trả |
| Ước tính thời lượng từ giả định mô phỏng | Thông báo trễ cho khách |
| Gợi ý lịch Line A / Line B | Override ưu tiên ảnh hưởng khách khác |
| Phát hiện rủi ro SLA và tác động sự cố | Nhận đơn mới khi đang cảnh báo năng lực |
| Soạn nháp thông điệp escalation | Phương án phục hồi cuối cùng khi SLA bị ảnh hưởng |

## 4. Luật phê duyệt (Human Approval Rules — PRD)

| Hành động | Cần duyệt | Lý do |
|---|:-:|---|
| Parse ticket, ước tính thời lượng | Không | Chuẩn bị nội bộ |
| Gán line còn trống, không ảnh hưởng SLA | Không | Đảo ngược được, deterministic |
| Đổi giờ trả đã hứa | **Có** | Thay đổi cam kết với khách |
| Hoãn đơn do sự cố | **Có** | Kinh doanh phải sở hữu việc liên lạc khách |
| Override ưu tiên | **Có** | Có thể ảnh hưởng khách khác |
| Nhận đơn mới khi đang cảnh báo sự cố | **Có** | Có thể tăng rủi ro trả trễ |

LLM **không bao giờ** có quyền gọi hàm approve.
