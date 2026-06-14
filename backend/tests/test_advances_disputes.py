import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, User
from apps.advances.models import AdvancePolicy, AdvanceRequest
from apps.advances.services import create_advance_request
from apps.attendance.models import AttendanceRecord
from apps.disputes.models import Dispute, DisputeComment
from apps.notifications.models import WorkerPortalSession
from apps.payroll.models import DailyWageLedger, PayrollCycle, PayrollLine
from apps.payroll.services import lock_payroll


def authenticate(client, user, company, role):
    token = RefreshToken.for_user(user)
    token["company_id"] = str(company.id)
    token["role"] = role
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


@pytest.fixture
def hr(company):
    user = User.objects.create_user(
        phone="+971500009020", password="StrongTestPass!1", name="HR"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.HR)
    return user


@pytest.mark.django_db
def test_advance_policy_limits_active_requests_per_cycle(
    company, owner, supervisor, worker, roster
):
    AdvancePolicy.objects.create(
        company=company,
        minimum_service_days=0,
        minimum_amount=Decimal("10.00"),
        max_requests_per_cycle=1,
    )
    captured_at = timezone.make_aware(
        datetime.combine(roster.date, datetime.min.time())
    )
    attendance = AttendanceRecord.objects.create(
        company=company,
        roster_assignment=roster,
        worker=worker,
        site=roster.site,
        shift=roster.shift,
        work_date=roster.date,
        check_in_at=captured_at,
        check_out_at=captured_at,
        verification_method=AttendanceRecord.VerificationMethod.MANUAL,
        device_id="advance-test",
        supervisor=supervisor,
        original_captured_at=captured_at,
        status=AttendanceRecord.Status.APPROVED,
        idempotency_key="advance-test",
    )
    DailyWageLedger.objects.create(
        company=company,
        worker=worker,
        attendance=attendance,
        work_date=roster.date,
        net_estimate=Decimal("500.00"),
        gross_estimate=Decimal("500.00"),
    )

    create_advance_request(
        worker=worker,
        amount=Decimal("100.00"),
        acknowledgement=True,
        actor=owner,
    )

    with pytest.raises(ValidationError, match="active advance request"):
        create_advance_request(
            worker=worker,
            amount=Decimal("50.00"),
            acknowledgement=True,
            actor=owner,
        )


@pytest.mark.django_db
def test_disbursed_advance_becomes_deducted_when_payroll_locks(
    company, owner, worker
):
    today = timezone.localdate()
    cycle = PayrollCycle.objects.create(
        company=company,
        name="Current payroll",
        period_start=today.replace(day=1),
        period_end=today,
        status=PayrollCycle.Status.APPROVED,
    )
    PayrollLine.objects.create(
        company=company,
        cycle=cycle,
        worker=worker,
        contract_basic=worker.basic_wage,
        regular_pay=Decimal("500.00"),
        advance_deductions=Decimal("100.00"),
        gross_pay=Decimal("500.00"),
        calculated_net_pay=Decimal("400.00"),
        net_pay=Decimal("400.00"),
    )
    advance = AdvanceRequest.objects.create(
        company=company,
        worker=worker,
        requested_amount=Decimal("100.00"),
        available_limit_snapshot=Decimal("200.00"),
        approved_amount=Decimal("100.00"),
        acknowledgement=True,
        acknowledgement_text="Deduct from payroll.",
        status=AdvanceRequest.Status.DISBURSED,
        deduction_cycle=cycle,
    )

    lock_payroll(cycle, owner)

    advance.refresh_from_db()
    assert advance.status == AdvanceRequest.Status.DEDUCTED


@pytest.mark.django_db
def test_dispute_requires_hr_to_resolve(
    api_client, company, owner, supervisor, worker, hr
):
    dispute = Dispute.objects.create(
        company=company,
        worker=worker,
        dispute_type=Dispute.Type.WRONG_DEDUCTION,
        date_reference=timezone.localdate(),
        description="Unexpected deduction.",
        status=Dispute.Status.SUPERVISOR_REVIEW,
        assigned_to=supervisor,
        sla_due_at=timezone.now(),
    )
    authenticate(api_client, supervisor, company, Membership.Role.SUPERVISOR)
    denied = api_client.post(
        f"/api/v1/disputes/{dispute.id}/resolve/",
        {"resolution": "Accepted"},
        format="json",
    )
    assert denied.status_code == 403

    escalated = api_client.post(
        f"/api/v1/disputes/{dispute.id}/escalate/",
        {},
        format="json",
    )
    assert escalated.status_code == 200
    assert escalated.data["status"] == Dispute.Status.HR_REVIEW

    authenticate(api_client, hr, company, Membership.Role.HR)
    resolved = api_client.post(
        f"/api/v1/disputes/{dispute.id}/resolve/",
        {"resolution": "Deduction was corrected."},
        format="json",
    )
    assert resolved.status_code == 200
    assert resolved.data["status"] == Dispute.Status.RESOLVED


@pytest.mark.django_db
def test_worker_portal_hides_internal_dispute_comments(
    api_client, company, supervisor, worker
):
    dispute = Dispute.objects.create(
        company=company,
        worker=worker,
        dispute_type=Dispute.Type.OTHER,
        date_reference=timezone.localdate(),
        description="Please review.",
        status=Dispute.Status.SUPERVISOR_REVIEW,
        assigned_to=supervisor,
        sla_due_at=timezone.now(),
    )
    DisputeComment.objects.create(
        company=company,
        dispute=dispute,
        author=supervisor,
        body="Visible update",
        is_worker_visible=True,
    )
    DisputeComment.objects.create(
        company=company,
        dispute=dispute,
        author=supervisor,
        body="Internal review note",
        is_worker_visible=False,
    )
    raw_token = "worker-portal-test-token"
    WorkerPortalSession.objects.create(
        company=company,
        worker=worker,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=1),
        last_seen_at=timezone.now(),
    )

    response = api_client.get(
        "/api/v1/worker/disputes/",
        HTTP_AUTHORIZATION=f"Worker {raw_token}",
    )

    assert response.status_code == 200
    assert [comment["body"] for comment in response.data[0]["comments"]] == [
        "Visible update"
    ]
