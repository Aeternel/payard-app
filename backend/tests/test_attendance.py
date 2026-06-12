from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.attendance.models import AttendanceException, AttendanceRecord
from apps.attendance.services import check_in, check_out, decide_exception
from apps.payroll.services import calculate_attendance_wage


@pytest.mark.django_db
def test_check_in_is_idempotent(company, supervisor, roster):
    captured = timezone.now() - timedelta(minutes=1)
    first, created = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=captured,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-1",
        idempotency_key="same-request",
    )
    second, duplicate_created = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=captured,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-1",
        idempotency_key="same-request",
    )
    assert created is True
    assert duplicate_created is False
    assert first.id == second.id


@pytest.mark.django_db
def test_daily_wage_uses_decimal_calculation(company, supervisor, roster):
    end = timezone.localtime().replace(second=0, microsecond=0)
    start = end - timedelta(hours=9)
    roster.date = start.date()
    roster.shift.start_time = start.time()
    roster.shift.end_time = end.time()
    roster.shift.save(update_fields=["start_time", "end_time", "updated_at"])
    roster.save(update_fields=["date", "updated_at"])
    record, _ = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=start,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-1",
        idempotency_key="wage-request",
    )
    record = check_out(
        record=record,
        actor=supervisor,
        captured_at=end,
    )
    assert record.status == AttendanceRecord.Status.APPROVED
    ledger = calculate_attendance_wage(record)
    assert ledger.regular_minutes == 480
    assert ledger.regular_pay == Decimal("80.00")
    assert ledger.net_estimate == Decimal("80.00")


@pytest.mark.django_db
def test_supervisor_can_approve_assigned_site_exception(
    api_client, company, supervisor, roster
):
    captured_at = timezone.now() - timedelta(minutes=1)
    roster.shift.start_time = (timezone.localtime(captured_at) - timedelta(minutes=10)).time()
    roster.shift.save(update_fields=["start_time", "updated_at"])
    record, _ = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=captured_at,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-review",
        idempotency_key="review-request",
    )
    exception = record.exceptions.get(exception_type=AttendanceException.Type.LATE)

    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(supervisor)
    token["company_id"] = str(company.id)
    token["role"] = "supervisor"
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    response = api_client.post(
        f"/api/v1/attendance-exceptions/{exception.id}/decide/",
        {
            "outcome": AttendanceException.Decision.FULL_DAY,
            "reason": "Supervisor accepted the late arrival as a full day.",
        },
        format="json",
    )

    assert response.status_code == 200
    record.refresh_from_db()
    exception.refresh_from_db()
    assert exception.status == AttendanceException.Status.RESOLVED
    assert exception.decision == AttendanceException.Decision.FULL_DAY
    assert record.status == AttendanceRecord.Status.OPEN


@pytest.mark.django_db
def test_rejected_exception_rejects_attendance(company, supervisor, roster):
    captured_at = timezone.now() - timedelta(minutes=1)
    roster.shift.start_time = (timezone.localtime(captured_at) - timedelta(minutes=10)).time()
    roster.shift.save(update_fields=["start_time", "updated_at"])
    record, _ = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=captured_at,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-reject",
        idempotency_key="reject-request",
    )
    exception = record.exceptions.get(exception_type=AttendanceException.Type.LATE)

    decide_exception(
        exception=exception,
        actor=supervisor,
        outcome=AttendanceException.Decision.REJECTED,
        reason="Late arrival was not accepted for attendance.",
    )

    record.refresh_from_db()
    assert record.status == AttendanceRecord.Status.REJECTED


@pytest.mark.django_db
def test_half_day_outcome_caps_daily_wage_at_fifty_percent(
    company, supervisor, roster
):
    end = timezone.localtime().replace(second=0, microsecond=0)
    planned_start = end - timedelta(hours=9)
    actual_start = planned_start + timedelta(minutes=10)
    roster.date = planned_start.date()
    roster.shift.start_time = planned_start.time()
    roster.shift.end_time = end.time()
    roster.shift.save(update_fields=["start_time", "end_time", "updated_at"])
    roster.save(update_fields=["date", "updated_at"])
    record, _ = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=actual_start,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-half-day",
        idempotency_key="half-day-request",
    )
    record = check_out(
        record=record,
        actor=supervisor,
        captured_at=end,
    )
    exception = record.exceptions.get(exception_type=AttendanceException.Type.LATE)
    decide_exception(
        exception=exception,
        actor=supervisor,
        outcome=AttendanceException.Decision.HALF_DAY,
        reason="Supervisor marked the late shift as half-day attendance.",
    )

    record.refresh_from_db()
    ledger = calculate_attendance_wage(record)
    assert record.status == AttendanceRecord.Status.APPROVED
    assert record.outcome == AttendanceRecord.Outcome.HALF_DAY
    assert record.payable_fraction == Decimal("0.50")
    assert ledger.regular_minutes == 240
    assert ledger.regular_pay == Decimal("40.00")


@pytest.mark.django_db
def test_half_day_uses_company_deduction_percentage(company, supervisor, roster):
    company.policy.half_day_deduction_percentage = Decimal("25.00")
    company.policy.save(update_fields=["half_day_deduction_percentage", "updated_at"])
    end = timezone.localtime().replace(second=0, microsecond=0)
    planned_start = end - timedelta(hours=9)
    actual_start = planned_start + timedelta(minutes=10)
    roster.date = planned_start.date()
    roster.shift.start_time = planned_start.time()
    roster.shift.end_time = end.time()
    roster.shift.save(update_fields=["start_time", "end_time", "updated_at"])
    roster.save(update_fields=["date", "updated_at"])
    record, _ = check_in(
        company=company,
        actor=supervisor,
        roster_id=roster.id,
        captured_at=actual_start,
        verification_method=AttendanceRecord.VerificationMethod.ID,
        device_id="device-custom-half-day",
        idempotency_key="custom-half-day-request",
    )
    record = check_out(record=record, actor=supervisor, captured_at=end)
    exception = record.exceptions.get(exception_type=AttendanceException.Type.LATE)
    decide_exception(
        exception=exception,
        actor=supervisor,
        outcome=AttendanceException.Decision.HALF_DAY,
        reason="Apply the configured organization half-day deduction.",
    )

    record.refresh_from_db()
    ledger = calculate_attendance_wage(record)
    assert record.payable_fraction == Decimal("0.75")
    assert ledger.regular_minutes == 360
    assert ledger.regular_pay == Decimal("60.00")
