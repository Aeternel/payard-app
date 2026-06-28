from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, User
from apps.attendance.models import AttendanceRecord
from apps.compliance.models import ComplianceAlert
from apps.organizations.models import Company
from apps.sites.models import RosterAssignment, ShiftTemplate, Site


@pytest.mark.django_db
def test_worker_list_is_tenant_scoped(api_client, owner, company, worker):
    other = Company.objects.create(name="Other", slug="other", legal_name="Other LLC")
    other_user = User.objects.create_user(
        phone="+971500009099", password="StrongTestPass!1", name="Other Owner"
    )
    Membership.objects.create(user=other_user, company=other, role=Membership.Role.OWNER)
    token = RefreshToken.for_user(owner)
    token["company_id"] = str(company.id)
    token["role"] = "owner"
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    response = api_client.get("/api/v1/workers/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(worker.id)


@pytest.mark.django_db
def test_token_for_inactive_membership_is_rejected(api_client, owner, company):
    membership = owner.memberships.get(company=company)
    membership.is_active = False
    membership.save()
    token = RefreshToken.for_user(owner)
    token["company_id"] = str(company.id)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    response = api_client.get("/api/v1/workers/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_supervisor_loses_worker_access_when_site_assignment_expires(
    api_client, supervisor, company, worker, site
):
    link = site.supervisor_links.get(supervisor=supervisor)
    link.active_until = timezone.localdate() - timedelta(days=1)
    link.save(update_fields=["active_until"])

    token = RefreshToken.for_user(supervisor)
    token["company_id"] = str(company.id)
    token["role"] = Membership.Role.SUPERVISOR
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    response = api_client.get("/api/v1/workers/")

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_supervisor_only_sees_compliance_alerts_for_currently_supervised_sites(
    api_client, company, owner, supervisor, worker, site, shift
):
    today = timezone.localdate()
    supervised_roster = RosterAssignment.objects.create(
        company=company,
        worker=worker,
        site=site,
        shift=shift,
        date=today + timedelta(days=1),
        approved_by=owner,
    )
    supervised_attendance = AttendanceRecord.objects.create(
        company=company,
        roster_assignment=supervised_roster,
        worker=worker,
        site=site,
        shift=shift,
        work_date=supervised_roster.date,
        check_in_at=timezone.now(),
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="site-a",
        supervisor=supervisor,
        original_captured_at=timezone.now(),
        status=AttendanceRecord.Status.PENDING,
        idempotency_key="supervised-compliance",
    )
    other_site = Site.objects.create(company=company, name="Other Site")
    other_shift = ShiftTemplate.objects.create(
        company=company,
        name="Other Shift",
        start_time=shift.start_time,
        end_time=shift.end_time,
    )
    other_roster = RosterAssignment.objects.create(
        company=company,
        worker=worker,
        site=other_site,
        shift=other_shift,
        date=today + timedelta(days=2),
        approved_by=owner,
    )
    other_attendance = AttendanceRecord.objects.create(
        company=company,
        roster_assignment=other_roster,
        worker=worker,
        site=other_site,
        shift=other_shift,
        work_date=other_roster.date,
        check_in_at=timezone.now(),
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="site-b",
        supervisor=owner,
        original_captured_at=timezone.now(),
        status=AttendanceRecord.Status.PENDING,
        idempotency_key="unsupervised-compliance",
    )
    visible_alert = ComplianceAlert.objects.create(
        company=company,
        alert_type="attendance_gap",
        severity=ComplianceAlert.Severity.WARNING,
        title="Visible attendance issue",
        description="Supervisor should see this.",
        entity_type="attendance.attendancerecord",
        entity_id=supervised_attendance.id,
        occurrence_date=supervised_roster.date,
        unique_key="visible-alert",
    )
    ComplianceAlert.objects.create(
        company=company,
        alert_type="attendance_gap",
        severity=ComplianceAlert.Severity.WARNING,
        title="Hidden attendance issue",
        description="Supervisor should not see this.",
        entity_type="attendance.attendancerecord",
        entity_id=other_attendance.id,
        occurrence_date=other_roster.date,
        unique_key="hidden-alert",
    )

    token = RefreshToken.for_user(supervisor)
    token["company_id"] = str(company.id)
    token["role"] = Membership.Role.SUPERVISOR
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    response = api_client.get("/api/v1/compliance-alerts/")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(visible_alert.id)
