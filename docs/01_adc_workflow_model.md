# ADC Workflow Model

## Actors

| Actor | Responsibility |
|---|---|
| Business | Create customer tickets, track customer promises, receive escalation notices |
| SX Production | Monitor incoming tickets, irradiation calendars, line status, incidents, and HITL approvals |
| Warehousing | Prepare receiving, staging, and return handover based on shared ticket and SX calendar state |

## Normal Flow

```mermaid
flowchart LR
    A[Business creates customer ticket] --> B[Order Agent extracts required fields]
    B --> C[Scheduler estimates processing duration]
    C --> D[Assign to LINE_A or LINE_B]
    D --> E[SX sees irradiation calendar]
    D --> F[Warehousing sees receiving and return calendar]
    E --> G[Work order completes]
    F --> H[Customer handover]
```

## Incident Flow

```mermaid
flowchart TD
    A[SX reports line downtime] --> B[Risk Agent finds affected work orders]
    B --> C[Check alternate line capacity]
    C --> D{Can protect high-priority orders?}
    D -->|Yes| E[Move orders and regenerate calendars]
    D -->|No| F[Escalate to Business]
    E --> G[Block risky new intake]
    F --> G
    G --> H[Request HITL approval]
    H --> I[SX approves recovery plan]
```

## Agent Responsibilities

| Agent | Responsibility |
|---|---|
| Order Agent | Convert business ticket into structured work-order input |
| Scheduler Agent | Estimate duration and assign orders to irradiation lines |
| Risk/Incident Agent | Detect affected orders, move work, block intake, and mark escalations |
| Notification Agent | Surface alerts to Business, SX, and Warehousing |

