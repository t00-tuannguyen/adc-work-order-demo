# Đánh giá trích xuất ticket — ADC-001 (T-022)

- Model: `gpt-4o-mini` · chạy lúc 03/10/2026 10:35
- Bộ mẫu: `src/seed/pdfs/` — 16 PDF giả lập (10 văn bản số, 6 scan), 18 ticket, đáp án `answers.json`
- Chấm trên kết quả **sau chuẩn hóa** (như lưu vào work order). Độ tin cậy do openai tự chấm (ADR-0010, ADR-0013).

| Chỉ số | Văn bản số | Scan | Tất cả | Mục tiêu |
|---|---|---|---|---|
| Độ chính xác trường | 92.0% | 62.5% | 80.6% | ≥ 95% (số) · ≥ 85% (scan) |
| Phát hiện đúng trường thiếu | 100.0% | 85.7% | 93.3% | 100% |
| Trang nguồn đúng | 100.0% | 100.0% | 100.0% | — |
| Khoảng trang ticket đúng | 100.0% | 100.0% | 100.0% | — |
| Tỷ lệ AUTO sai | 33.3% | — | 33.3% | ≈ 0 |
| Số ticket nhận đúng (file) | 10/10 | 6/6 | 16/16 | 100% |
| Lời gọi lỗi | 0 | 0 | 0 | 0 |
| Độ trễ TB / max (s) | 9.4 / 15.6 | 10.1 / 19.2 | 9.7 / 19.2 | < 10 s (PDF 1 trang) |

Quyết định cổng (tất cả ticket): AUTO 3, WARN 3, REVIEW 0, CLARIFY 12 · AUTO sai 1/3

## Độ chính xác theo trường

| Trường | Văn bản số | Scan |
|---|---|---|
| product_name | 72.7% | 42.9% |
| quantity | 100.0% | 71.4% |
| package_dimensions_cm | 81.8% | 57.1% |
| pkg_weight_kg | 100.0% | 85.7% |
| required_dose_kgy | 100.0% | 57.1% |
| priority | 100.0% | 85.7% |
| expected_arrival | 90.9% | 57.1% |
| requested_return | 90.9% | 42.9% |

## Từng mẫu

| Mẫu | Loại | Ticket (đáp án/nhận) | Trường sai | Quyết định | Ghi chú |
|---|---|---|---|---|---|
| 01_phieu_giavi | text | 1/1 | — | AUTO | Phiếu yêu cầu đủ 8 trường (TC1, TC11) |
| 02_phieu_haisan_vip | text | 1/1 | — | CLARIFY | Phiếu đủ trường, ưu tiên VIP ghi rõ |
| 03_email_2lo | text | 2/2 | t1.product_name, t1.package_dimensions_cm, t2.product_name | CLARIFY, CLARIFY | 1 file 2 ticket (TC4): lô 1 inch/lb + 'gấp' + 'mai' (TC7, suy luận); lô 2 thiếu liều + giờ trả (TC3) |
| 04_phieu_thieu_lieu | text | 1/1 | — | CLARIFY | Thiếu liều + giờ trả + ưu tiên (TC3) |
| 05_phieu_tra_truoc_den | text | 1/1 | — | CLARIFY | Giờ trả trước giờ hàng đến (TC8) — trích đúng giá trị, validator bắt lỗi |
| 06_email_don_vi_anh | text | 1/1 | t1.product_name, t1.package_dimensions_cm | AUTO | Email tiếng Anh, đơn vị inch/lb (TC7) |
| 07_phieu_lieu_7 | text | 1/1 | — | CLARIFY | Liều 7 kGy ngoài danh mục — trích đúng, validator hỏi lại |
| 08_phieu_2trang | text | 1/1 | — | AUTO | 1 ticket trải 2 trang (không được tách thành 2 lệnh) |
| 09_phieu_vattu_yte | text | 1/1 | — | CLARIFY | Vật tư y tế, 25 kGy, trả ngày hôm sau |
| 10_email_traicay_gam | text | 1/1 | t1.expected_arrival, t1.requested_return | WARN | Email, khối lượng theo gam, ngày tương đối 'thứ Hai tới', không nêu ưu tiên |
| 11_scan_phieu_giavi | scan | 1/1 | t1.product_name, t1.package_dimensions_cm, t1.pkg_weight_kg, t1.required_dose_kgy, t1.requested_return | CLARIFY | Bản scan của 01_phieu_giavi |
| 12_scan_email_2lo | scan | 2/2 | t1.product_name, t1.required_dose_kgy, t1.expected_arrival, t1.requested_return, t2.product_name, t2.quantity | CLARIFY, CLARIFY | Bản scan của 03_email_2lo |
| 13_scan_phieu_thieu_lieu | scan | 1/1 | — | CLARIFY | Bản scan của 04_phieu_thieu_lieu |
| 14_scan_email_don_vi_anh | scan | 1/1 | t1.package_dimensions_cm, t1.priority | WARN | Bản scan của 06_email_don_vi_anh |
| 15_scan_phieu_vattu_yte | scan | 1/1 | t1.package_dimensions_cm, t1.required_dose_kgy, t1.expected_arrival, t1.requested_return | CLARIFY | Bản scan của 09_phieu_vattu_yte |
| 16_scan_tra_truoc_den_mo | scan | 1/1 | t1.product_name, t1.quantity, t1.expected_arrival, t1.requested_return | WARN | Bản scan của 05_phieu_tra_truoc_den |
