# Product Requirements Document

## Objective

Deliver a 4-week MVP showing AI-agent workflow orchestration for an ADC-style
irradiation business process.

## Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Business can create a customer ticket with product, quantity, package dimensions, weight, dose, priority, arrival, and requested return time |
| FR-02 | System estimates irradiation processing duration from quantity, volume, weight, density factor, dose factor, and handling buffer |
| FR-03 | System schedules work orders across LINE_A and LINE_B |
| FR-04 | SX can view incoming tickets, line status, irradiation calendar, incidents, and pending HITL approvals |
| FR-05 | SX can simulate downtime for a selected line and estimated duration |
| FR-06 | Incident workflow identifies affected orders and attempts to move them to available capacity |
| FR-07 | Higher-priority orders are protected before lower-priority orders |
| FR-08 | System blocks risky new intake while recovery is active |
| FR-09 | System escalates to Business when requested return time cannot be protected |
| FR-10 | SX can approve pending recovery plans through HITL |
| FR-11 | Warehousing can see tickets, SX calendar, and derived return calendar |

## Non-Functional Requirements

- Demo state must update across all role views.
- Scheduling logic must be deterministic and explainable for judges.
- The MVP must run locally without external services.
- UI must make the three user roles obvious during live demo.

## Acceptance Scenarios

1. Seed demo data and see scheduled work across both irradiation lines.
2. Switch from Business to SX to Warehousing and see consistent state.
3. Trigger LINE_A downtime and see affected orders, moved orders, escalated
   orders, blocked intake, and pending HITL approval.
4. Approve recovery and see approval state update.

## Risks

- Throughput data is simulated, so the team should explain it as scale-down MVP
  logic rather than real irradiation capacity.
- In-memory state is suitable for demo only.

