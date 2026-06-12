from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.organizations.models import Company
from apps.sites.models import RosterAssignment, Site
from apps.workforce.models import ConsentRecord, Worker, WorkerDocument

from .models import ComplianceAlert


def _alert(company, *, key, alert_type, severity, title, description, entity, date, metadata=None):
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
            "occurrence_date": date,
            "metadata": metadata or {},
        },
    )


@shared_task
def scan_compliance_alerts(company_id=None):
    companies = Company.objects.filter(is_active=True)
    if company_id:
        companies = companies.filter(pk=company_id)
    today = timezone.localdate()
    for company in companies:
        policy = getattr(company, "policy", None)
        if not policy:
            continue
        expiry_limit = today + timedelta(days=30)
        for document in WorkerDocument.objects.filter(
            company=company, expiry_date__range=(today, expiry_limit)
        ).select_related("worker"):
            _alert(
                company,
                key=f"document-expiry:{document.id}:{document.expiry_date}",
                alert_type="document_expiry",
                severity=ComplianceAlert.Severity.WARNING,
                title="Worker document expires soon",
                description=(
                    f"{document.worker.full_name}'s document expires on "
                    f"{document.expiry_date}."
                ),
                entity=document,
                date=today,
            )
        if policy.require_biometric_consent:
            workers = Worker.objects.filter(company=company, status=Worker.Status.ACTIVE)
            consented_ids = ConsentRecord.objects.filter(
                company=company,
                consent_type=ConsentRecord.ConsentType.BIOMETRIC,
                status=ConsentRecord.Status.GRANTED,
            ).values_list("worker_id", flat=True)
            for worker in workers.exclude(id__in=consented_ids):
                _alert(
                    company,
                    key=f"biometric-consent:{worker.id}",
                    alert_type="consent_gap",
                    severity=ComplianceAlert.Severity.CRITICAL,
                    title="Biometric consent missing",
                    description="Use a non-biometric fallback until valid consent is captured.",
                    entity=worker,
                    date=today,
                )
        if policy.midday_break_enabled:
            month_day = today.strftime("%m-%d")
            in_season = policy.midday_break_start_date <= month_day <= policy.midday_break_end_date
            if in_season:
                rosters = RosterAssignment.objects.filter(
                    company=company,
                    date=today,
                    site__environment__in=[
                        Site.Environment.OUTDOOR,
                        Site.Environment.MIXED,
                    ],
                    status=RosterAssignment.Status.SCHEDULED,
                ).select_related("site", "shift")
                for roster in rosters:
                    if (
                        roster.shift.start_time < policy.midday_break_end_time
                        and roster.shift.end_time > policy.midday_break_start_time
                    ):
                        _alert(
                            company,
                            key=f"midday-break:{roster.id}:{today}",
                            alert_type="midday_outdoor_work",
                            severity=ComplianceAlert.Severity.CRITICAL,
                            title="Outdoor roster overlaps midday work restriction",
                            description=(
                                "Review the shift, exemption, rest station, "
                                "and safety controls."
                            ),
                            entity=roster,
                            date=today,
                        )
        cutoff = timezone.now() - timedelta(hours=18)
        for attendance in AttendanceRecord.objects.filter(
            company=company,
            check_out_at__isnull=True,
            check_in_at__lt=cutoff,
        ):
            _alert(
                company,
                key=f"missing-checkout:{attendance.id}",
                alert_type="missing_checkout",
                severity=ComplianceAlert.Severity.WARNING,
                title="Attendance has no checkout",
                description="Resolve this record before payroll close.",
                entity=attendance,
                date=attendance.work_date,
            )
    return companies.count()
