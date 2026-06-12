from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.attendance.models import AttendanceException, AttendanceRecord, OvertimeRequest
from apps.core.services import record_audit
from apps.disputes.models import Dispute
from apps.sites.models import RosterAssignment
from apps.workforce.models import Worker

from .models import DailyWageLedger, PayrollCycle, PayrollLine

MONEY = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _allowance_for_day(worker, days_in_period=30):
    total = Decimal("0")
    for allowance in worker.allowances or []:
        amount = Decimal(str(allowance.get("amount", 0)))
        frequency = allowance.get("frequency", "monthly")
        if frequency == "daily":
            total += amount
        elif frequency == "monthly":
            total += amount / Decimal(days_in_period)
    return money(total)


def _allowance_for_period(worker):
    total = Decimal("0")
    for allowance in worker.allowances or []:
        amount = Decimal(str(allowance.get("amount", 0)))
        frequency = allowance.get("frequency", "monthly")
        if frequency == "monthly":
            total += amount
    return money(total)


def _staff_period_fraction(worker, cycle):
    employed_from = max(worker.employment_start_date, cycle.period_start)
    employed_until = min(
        worker.employment_end_date or cycle.period_end,
        cycle.period_end,
    )
    if employed_until < employed_from:
        return Decimal("0")
    employed_days = Decimal((employed_until - employed_from).days + 1)
    cycle_days = Decimal((cycle.period_end - cycle.period_start).days + 1)
    return min(Decimal("1"), employed_days / cycle_days)


def _hourly_rate(worker, normal_daily_hours):
    normal_daily_hours = Decimal(normal_daily_hours)
    if worker.wage_type == Worker.WageType.HOURLY:
        return Decimal(worker.basic_wage)
    if worker.wage_type in {Worker.WageType.DAILY, Worker.WageType.SHIFT}:
        return Decimal(worker.basic_wage) / normal_daily_hours
    return Decimal(worker.basic_wage) / Decimal("30") / normal_daily_hours


def _scheduled_day_pay(worker, policy):
    if worker.wage_type == Worker.WageType.MONTHLY:
        regular = Decimal(worker.basic_wage) / Decimal("30")
    elif worker.wage_type in {Worker.WageType.DAILY, Worker.WageType.SHIFT}:
        regular = Decimal(worker.basic_wage)
    else:
        regular = Decimal(worker.basic_wage) * Decimal(policy.normal_daily_hours)
    allowance = _allowance_for_day(worker)
    return money(regular), allowance


def payroll_line_daily_breakdown(line):
    policy = getattr(line.company, "policy", None)
    if not policy:
        raise ValidationError("Company wage policy is not configured.")
    expected_regular, expected_allowance = _scheduled_day_pay(line.worker, policy)
    expected_total = money(expected_regular + expected_allowance)
    rosters = (
        RosterAssignment.objects.filter(
            company=line.company,
            worker=line.worker,
            date__range=(line.cycle.period_start, line.cycle.period_end),
        )
        .exclude(status__in=[RosterAssignment.Status.CANCELLED, RosterAssignment.Status.REPLACED])
        .select_related("site", "shift", "attendance", "attendance__wage_ledger")
        .prefetch_related("attendance__exceptions")
        .order_by("date")
    )
    entries = []
    running_total = Decimal("0")
    total_impact = Decimal("0")
    total_overtime = Decimal("0")
    for roster in rosters:
        attendance = getattr(roster, "attendance", None)
        ledger = getattr(attendance, "wage_ledger", None) if attendance else None
        regular_pay = ledger.regular_pay if ledger else Decimal("0")
        overtime_pay = ledger.overtime_pay if ledger else Decimal("0")
        allowances = ledger.allowances if ledger else Decimal("0")
        posted_deductions = ledger.deductions if ledger else Decimal("0")
        earned = ledger.net_estimate if ledger else Decimal("0")
        regular_and_allowance = money(regular_pay + allowances)
        pay_impact = max(Decimal("0"), money(expected_total - regular_and_allowance))
        if not attendance:
            day_type = "absent"
            attendance_status = "missing"
        elif attendance.status == AttendanceRecord.Status.REJECTED:
            day_type = "rejected"
            attendance_status = attendance.status
        elif attendance.outcome == AttendanceRecord.Outcome.HALF_DAY:
            day_type = "half_day"
            attendance_status = attendance.status
        elif attendance.status in {
            AttendanceRecord.Status.APPROVED,
            AttendanceRecord.Status.LOCKED,
        }:
            day_type = "full_day"
            attendance_status = attendance.status
        else:
            day_type = "pending"
            attendance_status = attendance.status
            pay_impact = Decimal("0")
        reasons = []
        if attendance:
            reasons = [
                exception.decision_reason or exception.reason
                for exception in attendance.exceptions.all()
                if exception.decision_reason or exception.reason
            ]
            if attendance.notes:
                reasons.append(attendance.notes)
        running_total = money(running_total + earned)
        total_impact = money(total_impact + pay_impact)
        total_overtime = money(total_overtime + overtime_pay)
        entries.append(
            {
                "date": roster.date,
                "site_name": roster.site.name,
                "shift_name": roster.shift.name,
                "day_type": day_type,
                "attendance_status": attendance_status,
                "check_in_at": attendance.check_in_at if attendance else None,
                "check_out_at": attendance.check_out_at if attendance else None,
                "payable_fraction": (
                    attendance.payable_fraction if attendance else Decimal("0")
                ),
                "expected_pay": expected_total,
                "regular_pay": regular_pay,
                "overtime_pay": overtime_pay,
                "allowances": allowances,
                "posted_deductions": posted_deductions,
                "earned_amount": earned,
                "pay_impact": pay_impact,
                "running_total": running_total,
                "reason": " · ".join(dict.fromkeys(reasons)),
                "ledger_status": ledger.status if ledger else "",
            }
        )
    return {
        "line": {
            "id": line.id,
            "cycle_id": line.cycle_id,
            "cycle_name": line.cycle.name,
            "period_start": line.cycle.period_start,
            "period_end": line.cycle.period_end,
            "cycle_status": line.cycle.status,
            "worker_id": line.worker_id,
            "worker_name": line.worker.full_name,
            "worker_code": line.worker.worker_code,
            "job_title": line.worker.job_title,
            "wage_type": line.worker.wage_type,
            "contract_basic": line.contract_basic,
            "calculated_net_pay": line.calculated_net_pay,
            "final_net_pay": line.net_pay,
            "manual_net_pay": line.manual_net_pay,
            "manual_override_reason": line.manual_override_reason,
        },
        "summary": {
            "scheduled_days": len(entries),
            "full_days": sum(entry["day_type"] == "full_day" for entry in entries),
            "half_days": sum(entry["day_type"] == "half_day" for entry in entries),
            "absent_or_rejected_days": sum(
                entry["day_type"] in {"absent", "rejected"} for entry in entries
            ),
            "daily_earned_total": running_total,
            "scheduled_pay_not_earned": total_impact,
            "overtime_total": total_overtime,
        },
        "entries": entries,
    }


@transaction.atomic
def calculate_attendance_wage(attendance):
    attendance = (
        AttendanceRecord.objects.select_related("worker", "company", "shift")
        .select_for_update()
        .get(pk=attendance.pk)
    )
    if attendance.status not in {
        AttendanceRecord.Status.APPROVED,
        AttendanceRecord.Status.LOCKED,
    }:
        raise ValidationError("Only approved attendance can be calculated.")
    if not attendance.check_out_at:
        raise ValidationError("Checkout is required.")
    policy = getattr(attendance.company, "policy", None)
    if not policy:
        raise ValidationError("Company wage policy is not configured.")
    total_minutes = max(
        0, int((attendance.check_out_at - attendance.check_in_at).total_seconds() // 60)
    )
    worked_minutes = max(0, total_minutes - attendance.shift.break_minutes)
    approved_overtime = (
        attendance.overtime_requests.filter(status=OvertimeRequest.Status.APPROVED).aggregate(
            total=Sum("approved_minutes")
        )["total"]
        or 0
    )
    regular_minutes = max(0, worked_minutes - approved_overtime)
    if attendance.outcome == AttendanceRecord.Outcome.HALF_DAY:
        payable_minutes = int(
            Decimal(policy.normal_daily_hours)
            * Decimal("60")
            * attendance.payable_fraction
        )
        regular_minutes = min(regular_minutes, payable_minutes)
    rate = _hourly_rate(attendance.worker, policy.normal_daily_hours)
    regular_pay = money(rate * Decimal(regular_minutes) / Decimal(60))
    multiplier = policy.overtime_multiplier
    if (
        attendance.shift.is_night_shift
        and not attendance.shift.shift_worker_exempt_from_night_premium
    ):
        multiplier = policy.night_overtime_multiplier
    overtime_pay = money(rate * Decimal(approved_overtime) / Decimal(60) * Decimal(multiplier))
    allowances = money(
        _allowance_for_day(attendance.worker) * attendance.payable_fraction
    )
    gross = money(regular_pay + overtime_pay + allowances)
    snapshot = {
        "worker_wage_type": attendance.worker.wage_type,
        "worker_basic_wage": str(attendance.worker.basic_wage),
        "hourly_rate": str(money(rate)),
        "normal_daily_hours": str(policy.normal_daily_hours),
        "break_minutes": attendance.shift.break_minutes,
        "overtime_multiplier": str(multiplier),
        "attendance_updated_at": attendance.updated_at.isoformat(),
        "attendance_outcome": attendance.outcome,
        "payable_fraction": str(attendance.payable_fraction),
    }
    ledger, _ = DailyWageLedger.objects.update_or_create(
        attendance=attendance,
        defaults={
            "company": attendance.company,
            "worker": attendance.worker,
            "work_date": attendance.work_date,
            "regular_minutes": regular_minutes,
            "overtime_minutes": approved_overtime,
            "regular_pay": regular_pay,
            "overtime_pay": overtime_pay,
            "allowances": allowances,
            "deductions": 0,
            "gross_estimate": gross,
            "net_estimate": gross,
            "calculation_snapshot": snapshot,
            "status": (
                DailyWageLedger.Status.FINAL
                if attendance.status == AttendanceRecord.Status.LOCKED
                else DailyWageLedger.Status.PROVISIONAL
            ),
        },
    )
    return ledger


def payroll_readiness(cycle):
    attendance = AttendanceRecord.objects.filter(
        company=cycle.company,
        work_date__range=(cycle.period_start, cycle.period_end),
    )
    active_workers = Worker.objects.filter(
        company=cycle.company,
        status=Worker.Status.ACTIVE,
        employment_start_date__lte=cycle.period_end,
    ).filter(
        models.Q(employment_end_date__isnull=True)
        | models.Q(employment_end_date__gte=cycle.period_start)
    )
    from apps.advances.models import AdvanceRequest

    checks = {
        "open_attendance": attendance.exclude(
            status__in=[AttendanceRecord.Status.APPROVED, AttendanceRecord.Status.LOCKED]
        ).count(),
        "missing_checkout": attendance.filter(check_out_at__isnull=True).count(),
        "open_attendance_exceptions": AttendanceException.objects.filter(
            company=cycle.company,
            attendance__work_date__range=(cycle.period_start, cycle.period_end),
            status=AttendanceException.Status.OPEN,
        ).count(),
        "pending_overtime": OvertimeRequest.objects.filter(
            company=cycle.company,
            attendance__work_date__range=(cycle.period_start, cycle.period_end),
            status=OvertimeRequest.Status.PENDING,
        ).count(),
        "unresolved_disputes": Dispute.objects.filter(
            company=cycle.company,
            date_reference__range=(cycle.period_start, cycle.period_end),
        )
        .exclude(status=Dispute.Status.RESOLVED)
        .count(),
        "unreconciled_advances": AdvanceRequest.objects.filter(
            company=cycle.company,
            deduction_cycle=cycle,
            status=AdvanceRequest.Status.DISBURSED,
        ).count(),
        "workers_missing_payroll_details": active_workers.filter(
            models.Q(payroll_method="") | models.Q(bank_account_or_card="")
        ).count(),
    }
    blockers = {key: value for key, value in checks.items() if value}
    total = sum(checks.values())
    return {
        "ready": not blockers,
        "score": max(0, 100 - min(100, total * 10)),
        "checks": checks,
        "blockers": blockers,
    }


@transaction.atomic
def build_payroll_lines(cycle, actor):
    cycle = PayrollCycle.objects.select_for_update().get(pk=cycle.pk)
    if cycle.status in {PayrollCycle.Status.LOCKED, PayrollCycle.Status.EXPORTED}:
        raise ValidationError("Locked payroll cannot be rebuilt.")
    workers = Worker.objects.filter(
        company=cycle.company,
        status=Worker.Status.ACTIVE,
        employment_start_date__lte=cycle.period_end,
    )
    from apps.advances.models import AdvanceRequest

    for worker in workers.iterator():
        ledger = DailyWageLedger.objects.filter(
            company=cycle.company,
            worker=worker,
            work_date__range=(cycle.period_start, cycle.period_end),
        ).aggregate(
            regular=Sum("regular_pay"),
            overtime=Sum("overtime_pay"),
            allowances=Sum("allowances"),
            deductions=Sum("deductions"),
        )
        regular = ledger["regular"] or Decimal("0")
        overtime = ledger["overtime"] or Decimal("0")
        allowances = ledger["allowances"] or Decimal("0")
        absence = ledger["deductions"] or Decimal("0")
        if worker.employment_category == Worker.EmploymentCategory.STAFF:
            staff_fraction = _staff_period_fraction(worker, cycle)
            regular = money(Decimal(worker.basic_wage) * staff_fraction)
            allowances = money(_allowance_for_period(worker) * staff_fraction)
            absence = Decimal("0")
        advances = AdvanceRequest.objects.filter(
            company=cycle.company,
            worker=worker,
            deduction_cycle=cycle,
            status__in=[
                AdvanceRequest.Status.DISBURSED,
                AdvanceRequest.Status.DEDUCTED,
            ],
        ).aggregate(total=Sum("approved_amount"))["total"] or Decimal("0")
        gross = money(regular + overtime + allowances)
        calculated_net = max(Decimal("0"), money(gross - absence - advances))
        existing_line = PayrollLine.objects.filter(cycle=cycle, worker=worker).first()
        manual_net_pay = existing_line.manual_net_pay if existing_line else None
        net = manual_net_pay if manual_net_pay is not None else calculated_net
        flags = []
        if worker.wage_type == Worker.WageType.MONTHLY and calculated_net < worker.basic_wage:
            flags.append("below_contract_baseline")
        if manual_net_pay is not None:
            flags.append("manual_net_override")
        PayrollLine.objects.update_or_create(
            cycle=cycle,
            worker=worker,
            defaults={
                "company": cycle.company,
                "contract_basic": worker.basic_wage,
                "regular_pay": regular,
                "overtime_pay": overtime,
                "allowances": allowances,
                "absence_deductions": absence,
                "advance_deductions": advances,
                "gross_pay": gross,
                "calculated_net_pay": calculated_net,
                "net_pay": net,
                "flags": flags,
                "calculation_snapshot": {
                    "generated_at": timezone.now().isoformat(),
                    "ledger_period": [str(cycle.period_start), str(cycle.period_end)],
                    "calculated_net_pay": str(calculated_net),
                    "manual_net_pay": (
                        str(manual_net_pay) if manual_net_pay is not None else None
                    ),
                },
            },
        )
    cycle.status = PayrollCycle.Status.REVIEW
    cycle.submitted_by = actor
    cycle.submitted_at = timezone.now()
    cycle.readiness_snapshot = payroll_readiness(cycle)
    cycle.save(
        update_fields=[
            "status",
            "submitted_by",
            "submitted_at",
            "readiness_snapshot",
            "updated_at",
        ]
    )
    record_audit(instance=cycle, action="payroll_built", actor=actor)
    return cycle


@transaction.atomic
def lock_payroll(cycle, actor):
    cycle = PayrollCycle.objects.select_for_update().get(pk=cycle.pk)
    if cycle.status != PayrollCycle.Status.APPROVED:
        raise ValidationError("Finance approval is required before payroll lock.")
    readiness = payroll_readiness(cycle)
    if not readiness["ready"]:
        raise ValidationError({"readiness": readiness})
    AttendanceRecord.objects.filter(
        company=cycle.company,
        work_date__range=(cycle.period_start, cycle.period_end),
        status=AttendanceRecord.Status.APPROVED,
    ).update(status=AttendanceRecord.Status.LOCKED)
    DailyWageLedger.objects.filter(
        company=cycle.company,
        work_date__range=(cycle.period_start, cycle.period_end),
    ).update(status=DailyWageLedger.Status.FINAL)
    cycle.status = PayrollCycle.Status.LOCKED
    cycle.locked_by = actor
    cycle.locked_at = timezone.now()
    cycle.readiness_snapshot = readiness
    cycle.save()
    record_audit(instance=cycle, action="payroll_locked", actor=actor)
    return cycle


# Kept local to avoid importing django.db.models as a broad public dependency.
from django.db import models  # noqa: E402
