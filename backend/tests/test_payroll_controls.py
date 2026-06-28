from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, User
from apps.attendance.models import AttendanceRecord
from apps.core.models import AuditLog
from apps.organizations.models import Company
from apps.payroll.models import DailyWageLedger, PayrollCycle, PayrollLine
from apps.sites.models import RosterAssignment
from apps.workforce.models import Worker


def authenticate(client, user, company, role):
    token = RefreshToken.for_user(user)
    token["company_id"] = str(company.id)
    token["role"] = role
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


@pytest.fixture
def hr(company):
    user = User.objects.create_user(
        phone="+971500009003", password="StrongTestPass!1", name="HR Manager"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.HR)
    return user


@pytest.fixture
def payroll_user(company):
    user = User.objects.create_user(
        phone="+971500009004", password="StrongTestPass!1", name="Payroll Operator"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.PAYROLL)
    return user


@pytest.fixture
def cycle(company):
    return PayrollCycle.objects.create(
        company=company,
        name="June 2026",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )


@pytest.fixture
def payroll_line(company, cycle, worker):
    return PayrollLine.objects.create(
        company=company,
        cycle=cycle,
        worker=worker,
        contract_basic=Decimal("1500.00"),
        regular_pay=Decimal("1500.00"),
        allowances=Decimal("300.00"),
        gross_pay=Decimal("1800.00"),
        calculated_net_pay=Decimal("1800.00"),
        net_pay=Decimal("1800.00"),
    )


@pytest.mark.django_db
def test_hr_can_update_half_day_policy(api_client, company, hr):
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.patch(
        f"/api/v1/payroll-settings/{company.policy.id}/",
        {"half_day_deduction_percentage": "35.00"},
        format="json",
    )

    assert response.status_code == 200
    company.policy.refresh_from_db()
    assert company.policy.half_day_deduction_percentage == Decimal("35.00")


@pytest.mark.django_db
def test_payroll_operator_cannot_update_management_policy(
    api_client, company, payroll_user
):
    authenticate(api_client, payroll_user, company, Membership.Role.PAYROLL)

    response = api_client.patch(
        f"/api/v1/payroll-settings/{company.policy.id}/",
        {"half_day_deduction_percentage": "35.00"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_hr_can_edit_draft_cycle_but_not_review_cycle(
    api_client, company, hr, cycle
):
    authenticate(api_client, hr, company, Membership.Role.HR)
    response = api_client.patch(
        f"/api/v1/payroll-cycles/{cycle.id}/",
        {"name": "June payroll"},
        format="json",
    )
    assert response.status_code == 200

    cycle.status = PayrollCycle.Status.REVIEW
    cycle.save(update_fields=["status", "updated_at"])
    response = api_client.patch(
        f"/api/v1/payroll-cycles/{cycle.id}/",
        {"name": "Unsafe rename"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_hr_can_build_draft_payroll_cycle(api_client, company, hr, cycle, worker):
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.post(
        f"/api/v1/payroll-cycles/{cycle.id}/build/",
        {},
        format="json",
    )

    assert response.status_code == 200
    cycle.refresh_from_db()
    assert cycle.status == PayrollCycle.Status.REVIEW
    assert cycle.lines.filter(worker=worker).exists()


@pytest.mark.django_db
def test_payroll_adjustment_rejects_cross_company_worker_and_cycle(
    api_client, company, owner
):
    other_company = Company.objects.create(
        name="Other Facilities",
        slug="other-facilities-adjustments",
        legal_name="Other Facilities LLC",
    )
    other_worker = Worker.objects.create(
        company=other_company,
        worker_code="OTHER-1",
        full_name="Other Worker",
        employment_start_date=date(2026, 6, 1),
        status=Worker.Status.ACTIVE,
        wage_type=Worker.WageType.DAILY,
        basic_wage=Decimal("100.00"),
        payroll_method="card",
        bank_account_or_card="other-card",
    )
    other_cycle = PayrollCycle.objects.create(
        company=other_company,
        name="Other June 2026",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )
    authenticate(api_client, owner, company, Membership.Role.OWNER)

    response = api_client.post(
        "/api/v1/payroll-adjustments/",
        {
            "cycle": str(other_cycle.id),
            "worker": str(other_worker.id),
            "source_type": "manual",
            "amount": "25.00",
            "reason": "Cross-company attempt",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["detail"] == {
        "cycle": ["Cross-company reference denied."],
        "worker": ["Cross-company reference denied."],
    }


@pytest.mark.django_db
def test_hr_override_preserves_calculated_pay_and_creates_audit(
    api_client, company, hr, cycle, payroll_line
):
    cycle.status = PayrollCycle.Status.REVIEW
    cycle.save(update_fields=["status", "updated_at"])
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.post(
        f"/api/v1/payroll-lines/{payroll_line.id}/override/",
        {
            "net_pay": "1725.00",
            "reason": "Approved unpaid leave correction.",
        },
        format="json",
    )

    assert response.status_code == 200
    payroll_line.refresh_from_db()
    assert payroll_line.calculated_net_pay == Decimal("1800.00")
    assert payroll_line.manual_net_pay == Decimal("1725.00")
    assert payroll_line.net_pay == Decimal("1725.00")
    assert payroll_line.manual_override_by == hr
    assert "manual_net_override" in payroll_line.flags
    assert AuditLog.objects.filter(
        company=company,
        entity_id=str(payroll_line.id),
        action="payroll_line_overridden",
    ).exists()


@pytest.mark.django_db
def test_approved_cycle_pay_cannot_be_overridden(
    api_client, company, hr, cycle, payroll_line
):
    cycle.status = PayrollCycle.Status.APPROVED
    cycle.save(update_fields=["status", "updated_at"])
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.post(
        f"/api/v1/payroll-lines/{payroll_line.id}/override/",
        {"net_pay": "1700.00", "reason": "Attempt after approval."},
        format="json",
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_daily_breakdown_shows_half_day_and_missing_roster_day(
    api_client,
    company,
    hr,
    cycle,
    payroll_line,
    roster,
    worker,
    site,
    shift,
    supervisor,
    owner,
):
    roster.date = cycle.period_start
    roster.save(update_fields=["date", "updated_at"])
    start = timezone.make_aware(datetime.combine(roster.date, shift.start_time))
    end = start + timedelta(hours=5)
    attendance = AttendanceRecord.objects.create(
        company=company,
        roster_assignment=roster,
        worker=worker,
        site=site,
        shift=shift,
        work_date=roster.date,
        check_in_at=start,
        check_out_at=end,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        source=AttendanceRecord.Source.ONLINE,
        device_id="payroll-detail-test",
        supervisor=supervisor,
        original_captured_at=start,
        status=AttendanceRecord.Status.APPROVED,
        outcome=AttendanceRecord.Outcome.HALF_DAY,
        payable_fraction=Decimal("0.50"),
        idempotency_key="payroll-detail-half-day",
    )
    DailyWageLedger.objects.create(
        company=company,
        worker=worker,
        attendance=attendance,
        work_date=roster.date,
        regular_minutes=240,
        regular_pay=Decimal("40.00"),
        gross_estimate=Decimal("40.00"),
        net_estimate=Decimal("40.00"),
    )
    RosterAssignment.objects.create(
        company=company,
        worker=worker,
        site=site,
        shift=shift,
        date=cycle.period_start + timedelta(days=1),
        approved_by=owner,
    )
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.get(
        f"/api/v1/payroll-lines/{payroll_line.id}/daily-breakdown/"
    )

    assert response.status_code == 200
    assert [entry["day_type"] for entry in response.data["entries"]] == [
        "half_day",
        "absent",
    ]
    assert response.data["entries"][0]["earned_amount"] == Decimal("40.00")
    assert response.data["entries"][0]["pay_impact"] == Decimal("40.00")
    assert response.data["entries"][1]["earned_amount"] == Decimal("0")
    assert response.data["entries"][1]["pay_impact"] == Decimal("80.00")
    assert response.data["summary"]["daily_earned_total"] == Decimal("40.00")
    assert response.data["summary"]["scheduled_pay_not_earned"] == Decimal("120.00")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("endpoint", "content_type", "signature"),
    [
        ("report-html", "text/html", b"<!doctype html>"),
        ("report-pdf", "application/pdf", b"%PDF"),
        (
            "report-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"PK",
        ),
    ],
)
def test_hr_can_download_payroll_reports(
    api_client,
    company,
    hr,
    cycle,
    payroll_line,
    endpoint,
    content_type,
    signature,
):
    cycle.status = PayrollCycle.Status.REVIEW
    cycle.save(update_fields=["status", "updated_at"])
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.get(f"/api/v1/payroll-cycles/{cycle.id}/{endpoint}/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith(content_type)
    assert response.content.startswith(signature)
    assert "payyard-" in response["Content-Disposition"]
    assert AuditLog.objects.filter(
        company=company,
        entity_id=str(cycle.id),
        action="payroll_report_downloaded",
        metadata__format=endpoint.removeprefix("report-"),
    ).exists()


@pytest.mark.django_db
def test_report_requires_built_payroll_lines(api_client, company, hr, cycle):
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.get(f"/api/v1/payroll-cycles/{cycle.id}/report-pdf/")

    assert response.status_code == 409


@pytest.mark.django_db
@override_settings(PAYROLL_REPORT_SYNC_MAX_ROWS=0)
def test_large_report_is_queued_as_background_artifact(
    api_client, company, hr, cycle, payroll_line
):
    cycle.status = PayrollCycle.Status.REVIEW
    cycle.save(update_fields=["status", "updated_at"])
    authenticate(api_client, hr, company, Membership.Role.HR)

    with patch("apps.payroll.views.generate_payroll_report.delay") as delay_mock:
        response = api_client.get(f"/api/v1/payroll-cycles/{cycle.id}/report-pdf/")

    assert response.status_code == 202
    assert response.data["export_type"] == "report_pdf"
    assert response.data["status"] == "pending"
    delay_mock.assert_called_once()
