# Product Brief

## Summary

Build an AI-agent workflow orchestration demo for irradiation business
operations. The system coordinates Business, SX Production, and Warehousing
around shared work-order state and incident recovery.

## Problem

In irradiation operations, schedule changes caused by line downtime can create
late customer returns. Manual coordination across Business, Warehouse, and SX is
slow and easy to desynchronize. A static dashboard can display the problem, but
it does not actively decide what should be moved, blocked, escalated, or sent to
human approval.

## Target Users

- Business staff handling customer promises.
- SX supervisors managing irradiation line calendars.
- Warehouse staff planning receiving, staging, and return handover.

## Value Proposition

The product demonstrates an AI-agent workflow that can orchestrate normal ticket
scheduling and react to incidents by checking alternate line capacity,
prioritizing orders, warning about intake risk, escalating customer-impacting
orders, and requesting HITL approval.

## MVP Success Criteria

- Business can create tickets from simple customer data.
- SX can simulate line downtime and review recovery output.
- Warehousing sees shared ticket state, SX calendar, and return calendar.
- An incident causes visible rescheduling, blocked intake, escalation, and HITL.
- All three role views stay synchronized.

