# Pitch Deck & Demo Materials — ADC Irradiation Work Order

## Files

- `pitch_deck.pptx` — Slide thuyết trình Demo Day
- `video_demo.mp4` — Video demo sản phẩm (tối đa 5 phút)

## Pitch Deck Structure (10 slides)

1. **Title** — ADC Irradiation Work Order · MFG 08 + Team
2. **Problem** — Kinh doanh hứa giờ trả trong khi năng lực line kiểm tra riêng; khi line dừng phải dựng lại lịch bằng tay → 4 rủi ro: trả trễ, line kém hiệu quả, ưu tiên sai, nhận đơn khi quá tải
3. **Solution** — Control tower multi-agent: đọc ticket PDF → ước tính → xếp Line A/B → xử lý sự cố → cảnh báo & escalation, **con người duyệt**
4. **Demo** — Kịch bản Line A incident (USP): Trước/Sau, đơn VIP sang Line B, đơn Thường escalate, plan chờ duyệt
5. **Architecture** — AI ở biên (đọc, giải thích, soạn thảo), luật deterministic ở lõi (tính lịch, rủi ro); sơ đồ trong `docs/architecture_diagram.md`
6. **Tech Stack** — FastAPI, LangGraph, OpenAI structured output, Next.js, Google OIDC
7. **Traction** — 6 Metrics PRD đo thực (`eval/results/report.md`), độ chính xác trích xuất trên bộ PDF mẫu, phản hồi đối tác
8. **Impact** — KPI 1 line vs 2 line: số đơn trễ, tổng phút trễ, % đúng giờ, hiệu suất line
9. **Team** — Ai làm gì (`docs/team.md`)
10. **Ask / Next** — PDF & dữ liệu thật từ đối tác, ngưỡng WARN/BLOCK, SSO Microsoft, solver tối ưu (OR-Tools) sau MVP

> Luôn ghi nhãn "Giá trị giả lập — không phải thông số vật lý chiếu xạ thật" trên slide có thời lượng/throughput.

## Video Demo Checklist

Chạy trên seed dataset cố định, reset trước khi quay (`docs/demo-scenarios.md`).

- [ ] Giới thiệu problem (< 30 giây)
- [ ] Normal order: tải PDF → form 8 trường có highlight → lịch trong < 5 giây
- [ ] Missing fields: yêu cầu bổ sung đúng trường, nút tạo lệnh bị khóa
- [ ] Line A incident: đề xuất < 10 giây, màn Trước/Sau, escalation + nháp AI, duyệt HITL
- [ ] New order during incident: banner WARN/BLOCK kèm giờ trả sớm nhất khả thi
- [ ] KPI & so sánh 1 line vs 2 line
- [ ] Tóm tắt impact (< 30 giây)

## Dự phòng khi pitch

- Tài khoản demo (feature flag `FEATURE_DEMO_LOGIN`) nếu Google/mạng lỗi.
- OCR và AI soạn thông điệp sau feature flag; tab "Dán nội dung" và nhập tay luôn bật.
