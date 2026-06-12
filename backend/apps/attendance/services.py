from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.services import record_audit
from apps.sites.models import RosterAssignment

from .models import AttendanceEvent, AttendanceException, AttendanceRecord


def _planned_start(roster):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(roster.date, roster.shift.start_time), tz)


def _planned_end(roster):
    end_date = roster.date + timedelta(days=1 if roster.shift.crosses_midnight else 0)
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(end_date, roster.shift.end_time), tz)


def _validate_capture_time(captured_at):
    now = timezone.now()
    if captured_at > now + timedelta(minutes=5):
        raise ValidationError({"captured_at": "Capture time cannot be in the future."})
    if captured_at < now - timedelta(days=7):
        raise ValidationError({"captured_at": "Offline records older than seven days need review."})


@transaction.atomic
def check_in(
    *,
    company,
    actor,
    roster_id,
    captured_at,
    verification_method,
    device_id,
    idempotency_key,
    source=AttendanceRecord.Source.ONLINE,
    photo=None,
    notes="",
):
    existing = AttendanceRecord.objects.filter(
        company=company, idempotency_key=idempotency_key
    ).first()
    if existing:
        return existing, False
    _validate_capture_time(captured_at)
    roster = (
        RosterAssignment.objects.select_for_update()
        .select_related("worker", "site", "shift")
        .filter(pk=roster_id, company=company, status=RosterAssignment.Status.SCHEDULED)
        .first()
    )
    if not roster:
        raise ValidationError({"roster_assignment": "Active roster assignment not found."})
    if (
        actor.memberships.get(company=company).role == "supervisor"
        and not roster.site.supervisor_links.filter(supervisor=actor).exists()
    ):
        raise ValidationError("Supervisor is not assigned to this site.")
    if hasattr(roster, "attendance"):
        raise ValidationError("Worker is already checked in for this roster.")

    flags = []
    if captured_at > _planned_start(roster) + timedelta(minutes=5):
        flags.append(AttendanceException.Type.LATE)

    record = AttendanceRecord.objects.create(
        company=company,
        roster_assignment=roster,
        worker=roster.worker,
        site=roster.site,
        shift=roster.shift,
        work_date=roster.date,
        check_in_at=captured_at,
        verification_method=verification_method,
        source=source,
        device_id=device_id,
        supervisor=actor,
        original_captured_at=captured_at,
        synced_at=timezone.now() if source == AttendanceRecord.Source.OFFLINE_SYNC else None,
        status=AttendanceRecord.Status.PENDING if flags else AttendanceRecord.Status.OPEN,
        flags=sorted(set(flags)),
        notes=notes,
        photo=photo,
        idempotency_key=idempotency_key,
    )
    AttendanceEvent.objects.create(
        attendance=record,
        company=company,
        event_type="checked_in",
        actor=actor,
        occurred_at=captured_at,
        payload={"source": source, "flags": flags},
    )
    for flag in set(flags):
        AttendanceException.objects.create(
            company=company,
            attendance=record,
            exception_type=flag,
            reason="Check-in was recorded after the shift start tolerance.",
        )
    record_audit(instance=record, action="attendance_checked_in", actor=actor)
    return record, True


@transaction.atomic
def check_out(*, record, actor, captured_at, notes=""):
    record = AttendanceRecord.objects.select_for_update().select_related("shift").get(pk=record.pk)
    if record.status == AttendanceRecord.Status.LOCKED:
        raise ValidationError("Locked attendance cannot be changed.")
    if record.status == AttendanceRecord.Status.REJECTED:
        raise ValidationError("Rejected attendance cannot be checked out.")
    if record.check_out_at:
        raise ValidationError("Worker is already checked out.")
    if captured_at < record.check_in_at:
        raise ValidationError({"captured_at": "Checkout cannot be before check-in."})
    _validate_capture_time(captured_at)
    flags = set(record.flags)
    if captured_at < _planned_end(record.roster_assignment) - timedelta(minutes=5):
        flags.add(AttendanceException.Type.EARLY_LEAVE)
    record.check_out_at = captured_at
    record.flags = sorted(flags)
    record.notes = "\n".join(filter(None, [record.notes, notes]))
    record.save(
        update_fields=[
            "check_out_at",
            "flags",
            "notes",
            "updated_at",
        ]
    )
    AttendanceEvent.objects.create(
        attendance=record,
        company=record.company,
        event_type="checked_out",
        actor=actor,
        occurred_at=captured_at,
        payload={"flags": sorted(flags)},
    )
    for flag in flags:
        AttendanceException.objects.get_or_create(
            company=record.company,
            attendance=record,
            exception_type=flag,
            defaults={
                "reason": (
                    "Checkout was recorded before the scheduled shift end."
                    if flag == AttendanceException.Type.EARLY_LEAVE
                    else "Check-in was recorded after the shift start tolerance."
                )
            },
        )
    if record.exceptions.filter(status=AttendanceException.Status.OPEN).exists():
        record.status = AttendanceRecord.Status.PENDING
    else:
        record.status = AttendanceRecord.Status.APPROVED
    record.save(update_fields=["status", "updated_at"])
    record_audit(instance=record, action="attendance_checked_out", actor=actor)
    if record.status == AttendanceRecord.Status.APPROVED:
        _queue_wage_recalculation(record)
    return record


@transaction.atomic
def decide_exception(*, exception, actor, outcome, reason):
    exception = AttendanceException.objects.select_for_update().get(pk=exception.pk)
    if exception.status != AttendanceException.Status.OPEN:
        raise ValidationError("Exception is already decided.")
    exception.decision = outcome
    exception.status = (
        AttendanceException.Status.REJECTED
        if outcome == AttendanceException.Decision.REJECTED
        else AttendanceException.Status.RESOLVED
    )
    exception.decided_by = actor
    exception.decided_at = timezone.now()
    exception.decision_reason = reason
    exception.save(
        update_fields=[
            "status",
            "decision",
            "decided_by",
            "decided_at",
            "decision_reason",
            "updated_at",
        ]
    )
    if outcome == AttendanceException.Decision.REJECTED:
        exception.attendance.exceptions.filter(
            status=AttendanceException.Status.OPEN
        ).exclude(pk=exception.pk).update(
            status=AttendanceException.Status.RESOLVED,
            decision=AttendanceException.Decision.REJECTED,
            decided_by=actor,
            decided_at=timezone.now(),
            decision_reason=f"Attendance rejected from another time exception: {reason}",
            updated_at=timezone.now(),
        )
    attendance = AttendanceRecord.objects.select_for_update().get(pk=exception.attendance_id)
    open_exceptions = attendance.exceptions.filter(
        status=AttendanceException.Status.OPEN
    ).exists()
    decisions = set(
        attendance.exceptions.exclude(decision="").values_list("decision", flat=True)
    )
    if AttendanceException.Decision.REJECTED in decisions:
        attendance.outcome = AttendanceRecord.Outcome.REJECTED
        attendance.payable_fraction = Decimal("0")
        attendance.status = AttendanceRecord.Status.REJECTED
    elif AttendanceException.Decision.HALF_DAY in decisions:
        attendance.outcome = AttendanceRecord.Outcome.HALF_DAY
        deduction_percentage = Decimal(
            getattr(attendance.company.policy, "half_day_deduction_percentage", 50)
        )
        attendance.payable_fraction = (
            Decimal("1") - (deduction_percentage / Decimal("100"))
        ).quantize(Decimal("0.01"))
        attendance.status = (
            AttendanceRecord.Status.PENDING
            if open_exceptions
            else (
                AttendanceRecord.Status.APPROVED
                if attendance.check_out_at
                else AttendanceRecord.Status.OPEN
            )
        )
    else:
        attendance.outcome = AttendanceRecord.Outcome.FULL_DAY
        attendance.payable_fraction = Decimal("1")
        attendance.status = (
            AttendanceRecord.Status.PENDING
            if open_exceptions
            else (
                AttendanceRecord.Status.APPROVED
                if attendance.check_out_at
                else AttendanceRecord.Status.OPEN
            )
        )
    attendance.save(
        update_fields=["status", "outcome", "payable_fraction", "updated_at"]
    )
    AttendanceEvent.objects.create(
        attendance=attendance,
        company=attendance.company,
        event_type=f"attendance_{outcome}",
        actor=actor,
        occurred_at=timezone.now(),
        payload={
            "exception_id": str(exception.id),
            "exception_type": exception.exception_type,
            "outcome": outcome,
            "reason": reason,
        },
    )
    if attendance.status == AttendanceRecord.Status.APPROVED:
        _queue_wage_recalculation(attendance)
    record_audit(
        instance=exception,
        action="attendance_exception_decided",
        actor=actor,
        metadata={"outcome": outcome},
    )
    return exception


def _queue_wage_recalculation(attendance):
    from apps.payroll.tasks import calculate_daily_wage

    transaction.on_commit(lambda: calculate_daily_wage.delay(str(attendance.id)))
