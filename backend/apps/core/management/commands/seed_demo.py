from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.advances.models import AdvancePolicy, AdvanceRequest
from apps.attendance.models import (
    AttendanceException,
    AttendanceRecord,
    OvertimeRequest,
)
from apps.compliance.models import ComplianceAlert
from apps.disputes.models import Dispute, DisputeComment
from apps.notifications.models import NotificationOutbox, NotificationTemplate
from apps.organizations.models import (
    Company,
    CompanyPolicy,
    FeatureFlag,
    WPSConfiguration,
)
from apps.payroll.models import DailyWageLedger, PayrollCycle, PayrollLine, WageRule
from apps.sites.models import RosterAssignment, ShiftTemplate, Site, SiteSupervisor
from apps.workforce.models import ConsentRecord, Worker, WorkerDocument

DEMO_PASSWORD = "PayYardDemo!2026"


class Command(BaseCommand):
    help = "Create an idempotent, presentation-ready PayYard demonstration tenant."

    def add_arguments(self, parser):
        parser.add_argument("--no-input", action="store_true")

    @staticmethod
    def aware(day, clock):
        return timezone.make_aware(
            datetime.combine(day, clock),
            timezone.get_current_timezone(),
        )

    def staff_user(self, *, company, phone, name, role, email=""):
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"name": name, "email": email},
        )
        if created or not user.has_usable_password():
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password", "updated_at"])
        Membership.objects.get_or_create(
            user=user,
            company=company,
            defaults={"role": role},
        )
        return user

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        company, _ = Company.objects.get_or_create(
            slug="payyard-demo",
            defaults={
                "name": "PayYard Demo Facilities",
                "legal_name": "PayYard Demo Facilities LLC",
                "emirate": "Dubai",
                "industry": "Facility management",
                "trade_license_number": "DEMO-TL-001",
                "mohre_establishment_number": "DEMO-MOHRE-1001",
            },
        )
        AttendanceException.objects.filter(company=company).exclude(
            exception_type__in=[
                AttendanceException.Type.LATE,
                AttendanceException.Type.EARLY_LEAVE,
            ]
        ).delete()
        for record in AttendanceRecord.objects.filter(company=company):
            time_flags = [
                flag
                for flag in record.flags
                if flag
                in {
                    AttendanceException.Type.LATE,
                    AttendanceException.Type.EARLY_LEAVE,
                }
            ]
            updates = []
            if time_flags != record.flags:
                record.flags = time_flags
                updates.append("flags")
            if (
                record.status == AttendanceRecord.Status.PENDING
                and not record.exceptions.filter(
                    status=AttendanceException.Status.OPEN
                ).exists()
            ):
                record.status = (
                    AttendanceRecord.Status.APPROVED
                    if record.check_out_at
                    else AttendanceRecord.Status.OPEN
                )
                updates.append("status")
            if updates:
                record.save(update_fields=[*updates, "updated_at"])
        CompanyPolicy.objects.get_or_create(company=company)
        WPSConfiguration.objects.get_or_create(
            company=company,
            defaults={
                "partner_name": "Demo Exchange House",
                "employer_bank_routing_code": "DEMO-BANK",
                "employer_account": "DEMO-EMPLOYER-ACCOUNT",
                "employer_reference": "PAYYARD-DEMO",
                "is_active": True,
            },
        )
        AdvancePolicy.objects.get_or_create(
            company=company,
            defaults={
                "maximum_amount": Decimal("750.00"),
                "max_requests_per_cycle": 2,
            },
        )
        for key, enabled in (
            ("worker-portal", True),
            ("salary-advances", True),
            ("offline-attendance", True),
            ("biometric-attendance", False),
        ):
            FeatureFlag.objects.get_or_create(
                company=company,
                key=key,
                defaults={"enabled": enabled},
            )

        owner = self.staff_user(
            company=company,
            phone="+971500000001",
            name="Demo Owner",
            role=Membership.Role.OWNER,
            email="owner@payyard.local",
        )
        downtown_supervisor = self.staff_user(
            company=company,
            phone="+971500000002",
            name="Omar Site Supervisor",
            role=Membership.Role.SUPERVISOR,
        )
        logistics_supervisor = self.staff_user(
            company=company,
            phone="+971500000003",
            name="Naveen Site Supervisor",
            role=Membership.Role.SUPERVISOR,
        )
        payroll_user = self.staff_user(
            company=company,
            phone="+971500000004",
            name="Maya Payroll Officer",
            role=Membership.Role.PAYROLL,
        )
        finance_user = self.staff_user(
            company=company,
            phone="+971500000005",
            name="Fatima Finance Manager",
            role=Membership.Role.FINANCE,
        )
        hr_user = self.staff_user(
            company=company,
            phone="+971500000006",
            name="Sara HR Officer",
            role=Membership.Role.HR,
        )
        operations_user = self.staff_user(
            company=company,
            phone="+971500000007",
            name="Ahmed Operations Manager",
            role=Membership.Role.OPERATIONS,
        )

        site_specs = [
            (
                "Downtown Tower A",
                downtown_supervisor,
                {
                    "client_name": "Demo Property Management",
                    "address": "Sheikh Mohammed bin Rashid Boulevard, Downtown Dubai",
                    "environment": Site.Environment.MIXED,
                },
            ),
            (
                "Jebel Ali Logistics Hub",
                logistics_supervisor,
                {
                    "client_name": "Gulf Logistics Demo",
                    "address": "Jebel Ali Industrial Area, Dubai",
                    "environment": Site.Environment.OUTDOOR,
                },
            ),
            (
                "Marina Hotel Residence",
                logistics_supervisor,
                {
                    "client_name": "Marina Hospitality Demo",
                    "address": "Dubai Marina, Dubai",
                    "environment": Site.Environment.INDOOR,
                },
            ),
        ]
        sites = {}
        for name, supervisor, defaults in site_specs:
            site, _ = Site.objects.get_or_create(
                company=company,
                name=name,
                defaults=defaults,
            )
            sites[name] = site
            SiteSupervisor.objects.get_or_create(
                company=company,
                site=site,
                supervisor=supervisor,
                defaults={"is_primary": True, "active_from": today - timedelta(days=180)},
            )

        day_shift, _ = ShiftTemplate.objects.get_or_create(
            company=company,
            name="Day shift",
            defaults={
                "start_time": time(8),
                "end_time": time(17),
                "break_minutes": 60,
            },
        )
        early_shift, _ = ShiftTemplate.objects.get_or_create(
            company=company,
            name="Early outdoor shift",
            defaults={
                "start_time": time(6),
                "end_time": time(14),
                "break_minutes": 60,
            },
        )
        night_shift, _ = ShiftTemplate.objects.get_or_create(
            company=company,
            name="Night security shift",
            defaults={
                "start_time": time(20),
                "end_time": time(6),
                "break_minutes": 60,
                "is_night_shift": True,
            },
        )

        worker_specs = [
            ("PY-0001", "Aamir Khan", "+971500001001", "Cleaner", "Downtown Tower A", "1500.00"),
            ("PY-0002", "Rafiq Ali", "+971500001002", "Cleaner", "Downtown Tower A", "1550.00"),
            (
                "PY-0003",
                "Suresh Kumar",
                "+971500001003",
                "Team helper",
                "Downtown Tower A",
                "1600.00",
            ),
            (
                "PY-0004",
                "Bikash Rai",
                "+971500001004",
                "Security guard",
                "Downtown Tower A",
                "1900.00",
            ),
            (
                "PY-0005",
                "Imran Hossain",
                "+971500001005",
                "Warehouse helper",
                "Jebel Ali Logistics Hub",
                "1700.00",
            ),
            (
                "PY-0006",
                "Manoj Thapa",
                "+971500001006",
                "Forklift assistant",
                "Jebel Ali Logistics Hub",
                "2100.00",
            ),
            (
                "PY-0007",
                "Abdul Rahman",
                "+971500001007",
                "Loader",
                "Jebel Ali Logistics Hub",
                "1650.00",
            ),
            (
                "PY-0008",
                "Nimal Perera",
                "+971500001008",
                "Storekeeper",
                "Jebel Ali Logistics Hub",
                "2300.00",
            ),
            (
                "PY-0009",
                "Joseph Dsouza",
                "+971500001009",
                "Housekeeping attendant",
                "Marina Hotel Residence",
                "1800.00",
            ),
            (
                "PY-0010",
                "Prakash Gurung",
                "+971500001010",
                "Maintenance helper",
                "Marina Hotel Residence",
                "2000.00",
            ),
            (
                "PY-0011",
                "Mohammed Salim",
                "+971500001011",
                "Security guard",
                "Marina Hotel Residence",
                "1950.00",
            ),
            (
                "PY-0012",
                "Arjun Tamang",
                "+971500001012",
                "Housekeeping attendant",
                "Marina Hotel Residence",
                "1750.00",
            ),
        ]
        workers = []
        for code, name, phone, job_title, site_name, wage in worker_specs:
            supervisor = (
                downtown_supervisor
                if site_name == "Downtown Tower A"
                else logistics_supervisor
            )
            worker, _ = Worker.objects.get_or_create(
                company=company,
                worker_code=code,
                defaults={
                    "full_name": name,
                    "phone": phone,
                    "nationality": "Demo nationality",
                    "job_title": job_title,
                    "employment_start_date": today - timedelta(days=240),
                    "status": Worker.Status.ACTIVE,
                    "wage_type": Worker.WageType.MONTHLY,
                    "basic_wage": Decimal(wage),
                    "allowances": [
                        {
                            "name": "Food allowance",
                            "amount": "300",
                            "frequency": "monthly",
                        }
                    ],
                    "payroll_method": "payroll_card",
                    "bank_routing_code": "DEMO001",
                    "bank_account_or_card": f"CARD-{code}",
                    "default_site": sites[site_name],
                    "supervisor": supervisor,
                },
            )
            workers.append(worker)

            for consent_type in (
                ConsentRecord.ConsentType.PRIVACY,
                ConsentRecord.ConsentType.LOCATION,
                ConsentRecord.ConsentType.NOTIFICATIONS,
            ):
                ConsentRecord.objects.get_or_create(
                    company=company,
                    worker=worker,
                    consent_type=consent_type,
                    version="demo-v1",
                    defaults={
                        "language": "en",
                        "channel": "admin",
                        "status": ConsentRecord.Status.GRANTED,
                        "captured_at": timezone.now() - timedelta(days=120),
                        "captured_by": hr_user,
                        "evidence": {"source": "demo seed"},
                    },
                )

        first_worker = workers[0]
        if not WorkerDocument.objects.filter(
            company=company,
            worker=first_worker,
            document_type=WorkerDocument.Type.WORK_PERMIT,
        ).exists():
            WorkerDocument.objects.create(
                company=company,
                worker=first_worker,
                document_type=WorkerDocument.Type.WORK_PERMIT,
                reference_number="DEMO-WP-0001",
                issue_date=today - timedelta(days=335),
                expiry_date=today + timedelta(days=25),
                status="verified",
                verified_at=timezone.now() - timedelta(days=120),
                verified_by=hr_user,
            )

        WageRule.objects.get_or_create(
            company=company,
            name="Standard monthly worker rule",
            effective_from=today.replace(month=1, day=1),
            defaults={
                "priority": 100,
                "configuration": {
                    "normal_hours": 8,
                    "overtime_multiplier": "1.25",
                    "monthly_divisor": 30,
                },
            },
        )

        shift_by_site = {
            "Downtown Tower A": day_shift,
            "Jebel Ali Logistics Hub": early_shift,
            "Marina Hotel Residence": day_shift,
        }
        roster_days = [today - timedelta(days=offset) for offset in range(0, 6)]
        rosters = {}
        for worker in workers:
            shift = (
                night_shift
                if worker.job_title == "Security guard"
                else shift_by_site[worker.default_site.name]
            )
            for work_day in roster_days:
                roster, _ = RosterAssignment.objects.get_or_create(
                    company=company,
                    worker=worker,
                    date=work_day,
                    defaults={
                        "site": worker.default_site,
                        "shift": shift,
                        "approved_by": operations_user,
                    },
                )
                rosters[(worker.id, work_day)] = roster

        for worker_index, worker in enumerate(workers):
            for day_index, work_day in enumerate(roster_days[1:], start=1):
                roster = rosters[(worker.id, work_day)]
                start = roster.shift.start_time
                check_in = self.aware(work_day, start) + timedelta(
                    minutes=(worker_index + day_index) % 5
                )
                duration = timedelta(hours=9)
                attendance, _ = AttendanceRecord.objects.get_or_create(
                    company=company,
                    roster_assignment=roster,
                    defaults={
                        "worker": worker,
                        "site": roster.site,
                        "shift": roster.shift,
                        "work_date": work_day,
                        "check_in_at": check_in,
                        "check_out_at": check_in + duration,
                        "verification_method": AttendanceRecord.VerificationMethod.ID,
                        "source": AttendanceRecord.Source.ONLINE,
                        "device_id": f"demo-device-{worker.supervisor_id}",
                        "supervisor": worker.supervisor,
                        "original_captured_at": check_in,
                        "status": AttendanceRecord.Status.APPROVED,
                        "idempotency_key": f"demo-{worker.worker_code}-{work_day}",
                    },
                )
                regular_pay = (worker.basic_wage / Decimal("30")).quantize(Decimal("0.01"))
                allowance = Decimal("10.00")
                DailyWageLedger.objects.get_or_create(
                    company=company,
                    attendance=attendance,
                    defaults={
                        "worker": worker,
                        "work_date": work_day,
                        "regular_minutes": 480,
                        "regular_pay": regular_pay,
                        "allowances": allowance,
                        "gross_estimate": regular_pay + allowance,
                        "net_estimate": regular_pay + allowance,
                        "calculation_snapshot": {"source": "demo seed"},
                    },
                )

        for worker_index, worker in enumerate(workers[:9]):
            roster = rosters[(worker.id, today)]
            check_in = self.aware(today, roster.shift.start_time) + timedelta(
                minutes=18 if worker_index == 1 else worker_index % 4
            )
            flags = []
            if worker_index == 1:
                flags = [AttendanceException.Type.LATE]
            attendance, _ = AttendanceRecord.objects.get_or_create(
                company=company,
                roster_assignment=roster,
                defaults={
                    "worker": worker,
                    "site": roster.site,
                    "shift": roster.shift,
                    "work_date": today,
                    "check_in_at": check_in,
                    "verification_method": AttendanceRecord.VerificationMethod.ID,
                    "source": AttendanceRecord.Source.ONLINE,
                    "device_id": f"demo-device-{worker.supervisor_id}",
                    "supervisor": worker.supervisor,
                    "original_captured_at": check_in,
                    "status": (
                        AttendanceRecord.Status.PENDING
                        if flags
                        else AttendanceRecord.Status.OPEN
                    ),
                    "flags": flags,
                    "idempotency_key": f"demo-{worker.worker_code}-{today}",
                },
            )
            for flag in flags:
                AttendanceException.objects.get_or_create(
                    company=company,
                    attendance=attendance,
                    exception_type=flag,
                    defaults={"reason": "Demo exception requiring supervisor review."},
                )

        overtime_attendance = AttendanceRecord.objects.get(
            roster_assignment=rosters[(workers[0].id, roster_days[1])]
        )
        OvertimeRequest.objects.get_or_create(
            company=company,
            attendance=overtime_attendance,
            requested_by=downtown_supervisor,
            defaults={
                "requested_minutes": 90,
                "approved_minutes": 60,
                "reason": "Emergency deep-cleaning after client event.",
                "status": OvertimeRequest.Status.APPROVED,
                "decided_by": operations_user,
                "decided_at": timezone.now() - timedelta(hours=12),
                "decision_reason": "Approved against client work order.",
            },
        )

        current_start = today.replace(day=1)
        current_end = (current_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        current_cycle, _ = PayrollCycle.objects.get_or_create(
            company=company,
            period_start=current_start,
            period_end=current_end,
            version=1,
            defaults={
                "name": current_start.strftime("%B %Y"),
                "readiness_snapshot": {
                    "score": 70,
                    "ready": False,
                    "blockers": {
                        "open_attendance": 9,
                        "open_attendance_exceptions": 2,
                    },
                },
            },
        )
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        previous_cycle, _ = PayrollCycle.objects.get_or_create(
            company=company,
            period_start=previous_start,
            period_end=previous_end,
            version=1,
            defaults={
                "name": previous_start.strftime("%B %Y"),
                "status": PayrollCycle.Status.APPROVED,
                "submitted_by": payroll_user,
                "approved_by": finance_user,
                "submitted_at": timezone.now() - timedelta(days=8),
                "approved_at": timezone.now() - timedelta(days=7),
                "readiness_snapshot": {"score": 100, "ready": True, "blockers": {}},
            },
        )
        payroll_lines = {}
        for index, worker in enumerate(workers):
            overtime_pay = Decimal("75.00") if index % 3 == 0 else Decimal("0.00")
            allowances = Decimal("300.00")
            absence = Decimal("50.00") if index == 6 else Decimal("0.00")
            gross = worker.basic_wage + allowances + overtime_pay
            net = gross - absence
            line, _ = PayrollLine.objects.get_or_create(
                company=company,
                cycle=previous_cycle,
                worker=worker,
                defaults={
                    "contract_basic": worker.basic_wage,
                    "regular_pay": worker.basic_wage,
                    "overtime_pay": overtime_pay,
                    "allowances": allowances,
                    "absence_deductions": absence,
                    "gross_pay": gross,
                    "net_pay": net,
                    "flags": ["absence_reviewed"] if absence else [],
                    "calculation_snapshot": {"source": "demo seed"},
                    "employer_reference": f"DEMO-{previous_start:%Y%m}-{worker.worker_code}",
                },
            )
            payroll_lines[worker.id] = line

        advance_specs = [
            (workers[0], "250.00", "250.00", AdvanceRequest.Status.DISBURSED),
            (workers[4], "300.00", "300.00", AdvanceRequest.Status.APPROVED),
            (workers[8], "200.00", "0.00", AdvanceRequest.Status.REQUESTED),
            (workers[2], "150.00", "0.00", AdvanceRequest.Status.REJECTED),
        ]
        for worker, requested, approved, status in advance_specs:
            AdvanceRequest.objects.get_or_create(
                company=company,
                worker=worker,
                requested_amount=Decimal(requested),
                defaults={
                    "available_limit_snapshot": Decimal("600.00"),
                    "approved_amount": Decimal(approved),
                    "acknowledgement": True,
                    "acknowledgement_text": (
                        "I understand this amount will be deducted from my payroll."
                    ),
                    "status": status,
                    "requested_via": "worker_portal",
                    "requested_by": owner,
                    "approved_by": (
                        finance_user
                        if status != AdvanceRequest.Status.REQUESTED
                        else None
                    ),
                    "approved_at": (
                        timezone.now() - timedelta(days=2)
                        if status != AdvanceRequest.Status.REQUESTED
                        else None
                    ),
                    "decision_reason": (
                        "Demo finance decision."
                        if status != AdvanceRequest.Status.REQUESTED
                        else ""
                    ),
                    "disbursed_at": (
                        timezone.now() - timedelta(days=1)
                        if status == AdvanceRequest.Status.DISBURSED
                        else None
                    ),
                    "disbursement_reference": (
                        "DEMO-DISBURSEMENT-001"
                        if status == AdvanceRequest.Status.DISBURSED
                        else ""
                    ),
                    "deduction_cycle": (
                        current_cycle if status == AdvanceRequest.Status.DISBURSED else None
                    ),
                },
            )

        dispute_specs = [
            (
                workers[1],
                Dispute.Type.OVERTIME_MISSING,
                Dispute.Status.SUPERVISOR_REVIEW,
                Dispute.Priority.HIGH,
                "One hour of approved overtime is missing from the wage preview.",
                downtown_supervisor,
            ),
            (
                workers[5],
                Dispute.Type.WRONG_SITE,
                Dispute.Status.HR_REVIEW,
                Dispute.Priority.NORMAL,
                "The roster showed Downtown although the worker reported at Jebel Ali.",
                hr_user,
            ),
            (
                workers[8],
                Dispute.Type.WRONG_DEDUCTION,
                Dispute.Status.OPEN,
                Dispute.Priority.URGENT,
                "The worker does not recognize an absence deduction.",
                logistics_supervisor,
            ),
            (
                workers[3],
                Dispute.Type.ABSENT_BUT_PRESENT,
                Dispute.Status.RESOLVED,
                Dispute.Priority.NORMAL,
                "Attendance was captured offline and initially appeared absent.",
                downtown_supervisor,
            ),
        ]
        for index, (worker, dispute_type, status, priority, description, assignee) in enumerate(
            dispute_specs
        ):
            dispute, _ = Dispute.objects.get_or_create(
                company=company,
                worker=worker,
                dispute_type=dispute_type,
                date_reference=today - timedelta(days=index + 1),
                defaults={
                    "description": description,
                    "status": status,
                    "priority": priority,
                    "assigned_to": assignee,
                    "raised_via": "worker_portal",
                    "sla_due_at": timezone.now() + timedelta(hours=12 + index * 12),
                    "resolution": (
                        "Offline record verified and attendance restored."
                        if status == Dispute.Status.RESOLVED
                        else ""
                    ),
                    "resolved_at": (
                        timezone.now() - timedelta(hours=8)
                        if status == Dispute.Status.RESOLVED
                        else None
                    ),
                    "resolved_by": hr_user if status == Dispute.Status.RESOLVED else None,
                    "linked_payroll_line": payroll_lines[worker.id],
                },
            )
            DisputeComment.objects.get_or_create(
                company=company,
                dispute=dispute,
                body="Demo case note: supporting records are being reviewed.",
                defaults={"author": assignee, "is_worker_visible": True},
            )

        alert_specs = [
            (
                "demo-document-expiry",
                "document_expiry",
                ComplianceAlert.Severity.WARNING,
                "Worker document expires soon",
                "Aamir Khan's work permit expires within 30 days.",
                first_worker,
            ),
            (
                "demo-consent-gap",
                "consent_gap",
                ComplianceAlert.Severity.CRITICAL,
                "Biometric consent missing",
                "Use ID verification until explicit biometric consent is captured.",
                workers[4],
            ),
            (
                "demo-midday-roster",
                "midday_outdoor_work",
                ComplianceAlert.Severity.CRITICAL,
                "Outdoor shift needs heat-control review",
                "Review midday break, exemption, hydration, and rest controls.",
                sites["Jebel Ali Logistics Hub"],
            ),
            (
                "demo-attendance-exception",
                "attendance_exception",
                ComplianceAlert.Severity.WARNING,
                "Attendance exceptions await decision",
                "Late and early-checkout exceptions should be cleared before payroll close.",
                workers[1],
            ),
            (
                "demo-payroll-readiness",
                "payroll_readiness",
                ComplianceAlert.Severity.INFO,
                "Current payroll cycle is 70% ready",
                "Open attendance and disputes are intentionally included in demo data.",
                current_cycle,
            ),
        ]
        for key, alert_type, severity, title, description, entity in alert_specs:
            ComplianceAlert.objects.get_or_create(
                company=company,
                unique_key=key,
                defaults={
                    "alert_type": alert_type,
                    "severity": severity,
                    "title": title,
                    "description": description,
                    "entity_type": entity._meta.label_lower,
                    "entity_id": entity.id,
                    "occurrence_date": today,
                    "metadata": {"source": "demo seed"},
                },
            )

        for channel in (
            NotificationTemplate.Channel.WHATSAPP,
            NotificationTemplate.Channel.SMS,
        ):
            NotificationTemplate.objects.get_or_create(
                company=company,
                key="worker_otp",
                channel=channel,
                language="en",
                defaults={
                    "body": (
                        "Your PayYard verification code is {{ code }}. "
                        "It expires in 5 minutes."
                    )
                },
            )
        NotificationTemplate.objects.get_or_create(
            company=company,
            key="attendance_exception",
            channel=NotificationTemplate.Channel.PUSH,
            language="en",
            defaults={
                "subject": "Attendance exception",
                "body": "{{ worker_name }} has an attendance exception requiring review.",
            },
        )
        NotificationOutbox.objects.get_or_create(
            company=company,
            idempotency_key="demo-attendance-notification-001",
            channel=NotificationTemplate.Channel.PUSH,
            defaults={
                "template_key": "attendance_exception",
                "recipient_user": downtown_supervisor,
                "subject": "Attendance exception",
                "rendered_body": (
                    "Rafiq Ali has a late-arrival exception requiring review."
                ),
                "context": {"worker_code": "PY-0002"},
                "status": NotificationOutbox.Status.DELIVERED,
                "scheduled_for": timezone.now() - timedelta(hours=1),
                "attempts": 1,
                "sent_at": timezone.now() - timedelta(minutes=59),
                "delivered_at": timezone.now() - timedelta(minutes=58),
            },
        )

        self.stdout.write(self.style.SUCCESS("Presentation-ready demo tenant is populated."))
        self.stdout.write(f"Company: {company.name}")
        self.stdout.write(f"Owner: +971500000001 / {DEMO_PASSWORD}")
        self.stdout.write(f"Supervisor A: +971500000002 / {DEMO_PASSWORD}")
        self.stdout.write(f"Supervisor B: +971500000003 / {DEMO_PASSWORD}")
        self.stdout.write(f"Payroll: +971500000004 / {DEMO_PASSWORD}")
        self.stdout.write(f"Finance: +971500000005 / {DEMO_PASSWORD}")
        self.stdout.write(f"HR: +971500000006 / {DEMO_PASSWORD}")
        self.stdout.write(f"Operations: +971500000007 / {DEMO_PASSWORD}")
        self.stdout.write("Worker portal phones: +971500001001 through +971500001012")
