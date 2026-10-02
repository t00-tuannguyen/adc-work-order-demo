# ADR-0004: Xếp lịch & ước tính bằng thuật toán deterministic

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 23/09/2026 |
| Liên quan | ADC-002, ADC-003, ADC-004 |

## Bối cảnh
Lịch phải tái lập được, không chồng lấn, giải thích được; không có dữ liệu năng suất thật và không được tính liều thật.

## Các phương án
| Vấn đề | Phương án bị loại | Lý do |
|---|---|---|
| Thời lượng | LLM ước tính | Không tái lập |
| Thời lượng | Huấn luyện ML | Không có dữ liệu thật (non-goal) |
| Thời lượng | Bảng tra theo sản phẩm | Bỏ qua số lượng và liều |
| Lịch | LLM xếp trực tiếp | Không tái lập, có thể chồng lấn |
| Lịch | Solver (OR-Tools) | Quá sức 6 tuần, khó giải thích → sau MVP |
| Sự cố | Chỉ báo động | Không giải quyết vấn đề |
| Sự cố | Dời tất cả tới sau khi sửa xong | Lãng phí line còn lại |

## Quyết định
- **Thời lượng:** công thức tuyến tính với tham số trong file cấu hình, làm tròn lên bội 15 phút.
- **Xếp lịch:** greedy *earliest feasible*; chọn line kết thúc sớm nhất, hòa → Line A.
- **Sự cố:** thuật toán 10 bước theo *Incident Handling Logic* của PRD; sắp VIP → Khẩn → Thường, rồi theo giờ trả.

## Hệ quả
- ✅ Cùng input + cấu hình → cùng kết quả (100%).
- ⚠️ Không tối ưu toàn cục — ghi rõ giới hạn; thể hiện hiệu quả qua KPI (ADC-007).
- ⚠️ Người xem có thể hiểu nhầm là mô hình vật lý → nhãn "Giá trị giả lập" trên UI và trong pitch.
