# PayYard

PayYard is a supervisor-first attendance-to-payroll operating system for UAE
site-based workforces. This repository implements the technical requirements
from the supplied product document and intentionally excludes sales material
and regulated money movement.

The system prepares payroll and WPS-style exports. It does not hold worker
funds, issue cards, lend money, or bypass a licensed bank, exchange house, or
WPS provider.

## Architecture

```text
Next.js web/PWA (hosted independently)
  Admin, payroll, finance, operations, supervisor, worker portal
        |
        | HttpOnly staff JWT / short-lived worker OTP session
        v
Django REST Framework modular monolith
  accounts        tenant memberships, roles, phone/password auth, devices
  organizations   company policy, WPS configuration, feature flags
  workforce       workers, documents, consent, worker portal
  sites           sites, shifts, rosters, supervisor access, transfers
  attendance      idempotent capture, offline sync, exceptions, overtime
  payroll         wage ledger, close workflow, locks, adjustments, exports
  advances        eligibility, approval, disbursement reference, deduction
  disputes        evidence, SLA, escalation, resolution, adjustment links
  compliance      heat, consent, document, and attendance alerts
  notifications   Firebase, WhatsApp, SMS, OTP, transactional outbox
  core            tenant viewsets, encryption, audit log, request context
        |
        +-- PostgreSQL: source of truth and relational constraints
        +-- RabbitMQ: Celery task broker
        +-- Redis: cache, throttling, Celery results
        +-- S3-compatible storage: optional private production file storage
```

Payroll-impacting actions use service functions and database transactions.
Attendance events and audit logs are append-only. Locked payroll data is not
silently overwritten; corrections are represented by adjustment records.
Large payroll artifacts are offloaded to Celery once a cycle exceeds the
configured synchronous row threshold.

## Local Development

Prerequisites: Docker Desktop or OrbStack, Docker Compose, Node.js 22+, and npm.

Backend infrastructure and services run in Docker:

```bash
docker compose up --build --remove-orphans
```

Next.js runs directly on the host in a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Configuration is intentionally split because the applications are deployed
independently:

- `backend/.env` belongs only to Django, Celery, PostgreSQL, Redis, RabbitMQ,
  Firebase, WhatsApp, SMS, and object storage configuration.
- `frontend/.env.local` belongs only to Next.js. Its server-only
  `INTERNAL_API_URL` points to the Django deployment.
- `backend/.env.example` and `frontend/.env.example` are deployment templates.

The included local development files let the project start immediately and are
ignored by Git. Replace every secret before using a shared environment.

- Web application: `http://localhost:3000`
- API: `http://localhost:8001/api/v1/`
- OpenAPI: `http://localhost:8001/api/docs/`
- Health: `http://localhost:8001/health/`
- Readiness: `http://localhost:8001/ready/`

Seeded staff credentials:

```text
Owner: +971500000001 / PayYardDemo!2026
Supervisor: +971500000002 / PayYardDemo!2026
```

Login requires only a phone number and password. See `MODULE_SUMMARY.md` for
all demo roles, credentials, and a concise description of every module.

The worker portal is at `http://localhost:3000/worker`. Demo worker numbers
start at `+971500001001`. Development OTP responses include a debug code.
Production never returns the code.

Useful commands:

```bash
make up
make frontend
make test
make lint
make migrations
make seed
```

## Security Model

- Every business row carries a company foreign key.
- JWTs carry one active company and are checked against live membership.
- Supervisors are additionally restricted to currently active site assignments
  and the workers attached to those active sites.
- Operational APIs are separated from self-service APIs by role-based
  permissions instead of relying only on tenant membership.
- Sensitive identifiers and payroll account fields use Fernet field
  encryption. Set an independent `FIELD_ENCRYPTION_KEY` outside development.
- Staff tokens are kept in HttpOnly cookies by the Next.js server layer.
- Worker sessions are OTP-derived, opaque, revocable, and expire after 12 hours.
- Offline attendance is AES-GCM encrypted in IndexedDB, expires after seven
  days, and syncs with an idempotency key and original capture timestamp.
- WhatsApp webhooks require an HMAC signature.
- Production S3 files are private, signed, and request server-side encryption.
- Deployment checks reject weak secrets, missing field encryption, and debug
  mode.

Run deployment checks before releasing:

```bash
docker compose run --rm backend python manage.py check --deploy \
  --settings=config.settings.production
```

## Environment And Integrations

Copy and fill the environment template owned by each deployment:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Backend configuration contains the Django secret, Fernet key, data services,
Firebase, WhatsApp, SMS, storage, and the public worker-portal URL. Frontend
configuration contains the server-only Django API URL; do not prefix it with
`NEXT_PUBLIC_` because authentication traffic must remain in Next.js route
handlers.

Operational flags:

- `APP_VERSION` surfaces the release version in health and readiness responses.
- `ENABLE_API_DOCS` should be `false` in staging and production unless you
  intentionally expose OpenAPI docs.
- `ENABLE_ADMIN` should be `false` in staging and production unless you
  intentionally rely on Django admin.
- `PAYROLL_REPORT_SYNC_MAX_ROWS` caps how many payroll lines can be rendered
  synchronously before the API queues a background artifact instead.

For separate production hosting:

- Set frontend `INTERNAL_API_URL=https://api.example.com/api/v1`.
- Set backend `WORKER_PORTAL_URL=https://app.example.com/worker`.
- Add the frontend origin to backend `CORS_ALLOWED_ORIGINS` and
  `CSRF_TRUSTED_ORIGINS`.
- Add the API hostname to backend `ALLOWED_HOSTS`.

Notification delivery uses a transactional outbox. Provider failures are
recorded and retried by Celery without rolling back the business transaction.

Payroll report generation supports two modes:

- Small cycles are streamed directly from `/api/v1/payroll-cycles/<id>/report-*`.
- Large cycles automatically return `202 Accepted`, create a `PayrollExport`
  artifact with `export_type` like `report_pdf`, and finish generation in
  Celery. Clients should poll `/api/v1/payroll-exports/` and use the returned
  `download_url` once the artifact reaches `ready`.

The Next.js staff UI is role-aware and now mirrors backend access boundaries:
attendance links are hidden from finance-only users, payroll links are hidden
from supervisor-only users, and large payroll report buttons switch from direct
download to queued-export status handling without exposing raw JSON responses.

## Production Checklist

1. Obtain UAE legal review for WPS formatting, wage rules, retention, consent,
   cross-border processing, and payment-partner boundaries.
2. Use an approved UAE/GCC region where required and managed PostgreSQL, Redis,
   RabbitMQ, and object storage with encryption and backups.
3. Put Django and Next.js behind a TLS-terminating load balancer and WAF.
4. Store each deployment's secrets in its own cloud secret manager, not local
   `.env` files.
5. Enable centralized logs, error tracking, queue monitoring, uptime checks,
   audit anomaly alerts, and tested backup restores.
6. Run migrations as a one-off release job before rolling application tasks.
7. Configure retention schedules and test deletion/anonymization procedures.
8. Load-test bulk attendance, offline sync, payroll close, and export generation
   at expected site concurrency.
9. Set a conservative `PAYROLL_REPORT_SYNC_MAX_ROWS` for your worker and memory
   budget so large payroll reports are always processed asynchronously.
