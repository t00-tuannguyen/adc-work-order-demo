# ADC Project Overview

## Project Name

AI Agent Workflow Orchestration in Irradiation Business

## Background

The project adapts the MFG-08 Work Order Orchestration idea to an ADC-style
business workflow: Business receives customer irradiation requests, Warehousing
coordinates receiving and return handover, and SX/Production runs irradiation
lines.

Customer tickets provide product quantity, package configuration, weight,
dimensions, required dose, priority, arrival time, and requested return time. The
MVP uses scale-down throughput assumptions to estimate processing duration and
schedule work across two irradiation lines.

## Core Demo Question

Can an AI-agent workflow coordinate normal scheduling and handle abnormal
production incidents better than a static dashboard?

## MVP Focus

- Three synchronized user views: Business, SX Production, and Warehousing.
- Ticket intake and scheduling for two irradiation lines.
- Incident recovery when one line goes down.
- Priority-aware rescheduling and escalation.
- Human-in-the-loop approval for customer-impacting changes.

## Out Of Scope

- Certified irradiation physics.
- Real ERP/MES/WMS integration.
- Persistent database and authentication.
- Production-grade optimization solver.

