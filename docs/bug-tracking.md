# Theo dõi lỗi

Nguồn: sheet *Theo dõi lỗi*. Khuyến nghị báo lỗi bằng GitHub Issue, tiêu đề `BUG-NNN: ...`, và đồng bộ sang Excel.

## Mẫu báo lỗi

```
Mã lỗi: BUG-NNN
Tiêu đề:
Mô tả:
Cách tái hiện: 1. … 2. … 3. …
Kết quả mong đợi / thực tế:
Mức nghiêm trọng: Nghiêm trọng | Cao | Trung bình | Thấp
Ưu tiên: P0–P3
Mã US / Task liên quan: US-xxx / T-xxx
Người xử lý:
Ngày phát hiện:
Trạng thái: Mở | Đang sửa | Đã sửa | Đóng
```

## Thang mức nghiêm trọng

| Mức | Định nghĩa |
|---|---|
| Nghiêm trọng | Ứng dụng sập hoặc mất dữ liệu — không dùng được |
| Cao | Tính năng chính sai, ảnh hưởng nhiều người dùng |
| Trung bình | Tính năng phụ lỗi, vẫn dùng được |
| Thấp | Lỗi nhỏ về giao diện |

**Luôn xếp Nghiêm trọng** với dự án này: thay đổi ảnh hưởng khách được kích hoạt khi chưa duyệt; 2 slot chồng lấn trên cùng line; thông điệp gửi khách khi chưa duyệt; truy cập dữ liệu từ tài khoản PENDING/DISABLED.
