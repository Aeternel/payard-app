# PayYard Module Summary

## Demo Access

All staff accounts use the password `PayYardDemo!2026`; login requires only the phone number and password.
Use `http://localhost:3000` for staff access and `http://localhost:3000/worker` for the OTP-based worker portal.

| Role | Phone | Access |
| --- | --- | --- |
| Owner | `+971500000001` | Full organization access across all sites |
| Downtown Supervisor | `+971500000002` | Downtown Tower A workers and operations |
| Logistics Supervisor | `+971500000003` | Jebel Ali and Marina site workers and operations |
| Payroll Officer | `+971500000004` | Wage rules, payroll building, and payroll review |
| Finance Manager | `+971500000005` | Finance approval, advances, payroll approval, and locking |
| HR Officer | `+971500000006` | Worker records, documents, consent, and dispute resolution |
| Operations Manager | `+971500000007` | Sites, rosters, attendance, transfers, and exceptions |

Worker portal demo numbers run from `+971500001001` to `+971500001012`.
In development, requesting an OTP returns a debug code in the API response; production never exposes it.

## Accounts

Provides globally unique phone/password authentication, HttpOnly JWT sessions, password changes, devices, company memberships, and role-based permissions.
Its purpose is to identify staff securely and automatically bind every session to the correct organization and allowed site scope.

## Organizations

Stores the company profile, payroll policy, WPS partner configuration, setup readiness, and configurable feature flags.
Its purpose is to keep organization-wide legal, payroll, and operational settings centralized and tenant-isolated.

## Workforce

Manages worker profiles, employment and wage details, encrypted payroll identifiers, documents, consent history, and worker self-service data.
Its purpose is to provide one reliable worker master record that attendance, payroll, advances, and disputes can safely reference.

## Sites

Manages sites, environments, supervisor assignments, shift templates, daily rosters, and worker transfers.
Its purpose is to model where workers operate and enforce site-level visibility for supervisors and operational workflows.

## Attendance

Supports online and encrypted offline check-in, checkout, time-based late/early exceptions, full-day/half-day/rejected decisions, immutable events, and overtime requests.
Its purpose is to turn site activity into auditable, payroll-ready attendance without collecting worker location data.

## Payroll

Calculates daily wage ledgers and manages versioned payroll cycles, readiness checks, approvals, locks, adjustments, and WPS-style exports.
Its purpose is to create a controlled attendance-to-payroll close process where finalized wage data cannot be silently rewritten.

## Advances

Defines company advance policies and tracks worker requests through eligibility, approval, disbursement reference, and payroll deduction.
Its purpose is to make salary advances transparent and reconcilable while leaving actual money movement to licensed providers.

## Disputes

Tracks worker issues with evidence, comments, ownership, priority, SLA escalation, resolution, and linked payroll adjustments.
Its purpose is to give attendance and wage complaints a visible, auditable path from worker submission to final decision.

## Compliance

Generates and manages operational alerts for expiring documents, missing consent, heat-risk rosters, attendance gaps, and payroll readiness.
Its purpose is to surface UAE workforce compliance risks early while keeping final legal decisions with qualified reviewers.

## Notifications

Provides templates and a transactional outbox for Firebase push, WhatsApp, SMS, OTP delivery, retries, and signed webhook handling.
Its purpose is to deliver business notifications reliably without allowing provider failures to roll back core payroll operations.

## Core

Provides tenant-scoped viewsets, encryption fields, immutable audit logs, request IDs, pagination, exception formatting, and security checks.
Its purpose is to supply shared production controls so every business module follows the same isolation and audit rules.

## Next.js Web Application

Provides responsive staff dashboards, site and payroll workflows, a worker OTP portal, and encrypted IndexedDB attendance queuing.
Its purpose is to give office and site teams a secure interface while keeping staff tokens inside the server-side BFF layer.

## Background Infrastructure

PostgreSQL is the source of truth, RabbitMQ carries Celery jobs, Redis supports caching and task results, and private object storage is available for files.
Its purpose is to keep transactional work, asynchronous delivery, caching, and sensitive documents independently scalable and recoverable.
