# ADR-0005: Phê duyệt HITL theo cả plan version

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 23/09/2026 |
| Liên quan | FR 12, ADC-006 |

## Bối cảnh
Một sự cố có thể thay đổi nhiều đơn cùng lúc. Thay đổi ảnh hưởng khách không được kích hoạt khi chưa duyệt.

## Các phương án
1. Duyệt từng đơn riêng lẻ — chi tiết nhưng rối khi 1 sự cố ảnh hưởng nhiều đơn.
2. **Duyệt/từ chối cả plan version**, bắt buộc ghi lý do khi từ chối.

## Quyết định
Chọn **2**. Version chứa ≥ 1 thay đổi thuộc 4 loại cần duyệt (đổi giờ trả, hoãn, override ưu tiên, nhận đơn khi cảnh báo) → `PENDING_APPROVAL`; ngược lại → `ACTIVE` ngay. Chỉ 1 version ACTIVE. Từ chối từng dòng thay đổi là "Nên có".

## Hệ quả
- ✅ 1 cổng duyệt duy nhất, dễ audit.
- ⚠️ Có sự cố mới khi version cũ đang chờ → version cũ SUPERSEDED.
- ⚠️ MVP không rollback tự động — hoàn tác bằng version mới.
