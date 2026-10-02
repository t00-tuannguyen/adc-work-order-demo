# Architecture Diagram — ADC Irradiation Work Order

Bản đầy đủ: [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## System Overview

```mermaid
graph TB
    User([Kinh doanh · Điều phối · Quản lý · Admin]) --> UI[Frontend<br/>Next.js]
    UI -->|REST /api, /auth| API[FastAPI Backend]
    API --> ORC[Orchestrator<br/>state · plan version · HITL]
    ORC --> Agents[Order / Scheduler / Risk Agent<br/>LangGraph + OpenAI, JSON schema]
    ORC --> Core[Lõi deterministic<br/>estimate · schedule · reschedule · risk]
    Agents --> VAL[Validator]
    Core --> CFG[[throughput.yaml]]
    ORC --> DB[(PostgreSQL / SQLite)]
    API --> AUTH[Google OIDC + RBAC]
```

## Luồng sự cố Line A (USP)

```mermaid
graph LR
    I[Khai báo sự cố<br/>Line A 09:00–12:00] --> F[Tìm slot chồng lấn]
    F --> SORT[Sắp VIP → Khẩn → Thường<br/>rồi theo giờ trả]
    SORT --> ALT{Line B còn khe?}
    ALT -->|có| MV[Dời sang Line B]
    ALT -->|không| DL[Xếp sau khi hồi phục<br/>DELAYED]
    MV & DL --> PV[Plan version mới]
    PV --> SLA{Trễ giờ trả?}
    SLA -->|có| ESC[SLA_RISK → Escalation<br/>AI soạn nháp]
    SLA -->|không| PA
    ESC --> PA[PENDING_APPROVAL]
    PA --> H[Người duyệt] --> ACT[ACTIVE]
```

## Component Details

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Next.js + TypeScript | Tiếp nhận, Kanban, timeline, duyệt, escalation, KPI |
| Backend | FastAPI | API, job PDF/OCR |
| Orchestrator | Code + LangGraph | Ghi trạng thái, gọi agent, áp luật duyệt |
| Agents | OpenAI `gpt-4o-mini`, structured output | Trích xuất, giải thích, soạn nháp |
| Lõi deterministic | Python thuần | Thời lượng, lịch, rủi ro, KPI |
| Database | SQLite → PostgreSQL | Work order, plan version, audit |
| Auth | Google OAuth 2.0 / OIDC | Đăng nhập, RBAC |
