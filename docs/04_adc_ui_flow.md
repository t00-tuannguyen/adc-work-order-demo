# UI Flow

## Role Switcher

The demo starts with three role buttons:

- Business
- SX Production
- Warehousing

All views use the same backend state so judges can see the effect of one role's
action in the other views.

## Business View

- Add customer ticket.
- See escalation and approval notifications.
- See customer promise board.

## SX Production View

- See line status for LINE_A and LINE_B.
- Trigger incident recovery.
- Review pending HITL approvals.
- See incoming tickets and incident recovery details.
- See irradiation calendar for both lines.

## Warehousing View

- See warehouse ticket queue.
- See return calendar derived from SX completion time.
- See SX calendar to prepare receiving and staging.

## Demo Script

1. Click `Seed demo`.
2. Show Business ticket board.
3. Switch to SX and trigger LINE_A incident.
4. Explain how the agent moves what can fit, escalates what cannot fit, and
   blocks risky new intake.
5. Approve the recovery plan.
6. Switch to Warehousing and show updated return calendar.

