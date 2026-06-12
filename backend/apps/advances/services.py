from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.services import record_audit
from apps.payroll.models import DailyWageLedger, PayrollCycle

from .models import AdvancePolicy, AdvanceRequest


def available_advance_limit(worker, cycle=None):
    policy = AdvancePolicy.objects.filter(company=worker.company, enabled=True).first()
    if not policy:
        return Decimal("0")
    if timezone.localdate() - worker.employment_start_date < timedelta(
        days=policy.minimum_service_days
    ):
        return Decimal("0")
    if cycle:
        start, end = cycle.period_start, cycle.period_end
    else:
        today = timezone.localdate()
        start, end = today.replace(day=1), today
    earned = DailyWageLedger.objects.filter(
        company=worker.company,
        worker=worker,
        work_date__range=(start, end),
    ).aggregate(total=Sum("net_estimate"))["total"] or Decimal("0")
    outstanding = AdvanceRequest.objects.filter(
        company=worker.company,
        worker=worker,
        status__in=[
            AdvanceRequest.Status.APPROVED,
            AdvanceRequest.Status.DISBURSED,
        ],
    ).aggregate(total=Sum("approved_amount"))["total"] or Decimal("0")
    limit = earned * policy.max_earned_wage_percentage / Decimal("100") - outstanding
    if policy.maximum_amount is not None:
        limit = min(limit, policy.maximum_amount)
    return max(Decimal("0"), limit.quantize(Decimal("0.01")))


@transaction.atomic
def create_advance_request(*, worker, amount, acknowledgement, actor=None, channel="admin"):
    policy = AdvancePolicy.objects.filter(company=worker.company, enabled=True).first()
    if not policy:
        raise ValidationError("Salary advances are not enabled.")
    if not acknowledgement:
        raise ValidationError({"acknowledgement": "Deduction acknowledgement is required."})
    limit = available_advance_limit(worker)
    if amount < policy.minimum_amount or amount > limit:
        raise ValidationError(
            {"amount": f"Amount must be between {policy.minimum_amount} and {limit}."}
        )
    request = AdvanceRequest.objects.create(
        company=worker.company,
        worker=worker,
        requested_amount=amount,
        available_limit_snapshot=limit,
        acknowledgement=True,
        acknowledgement_text=policy.acknowledgement_text,
        requested_by=actor,
        requested_via=channel,
    )
    record_audit(instance=request, action="advance_requested", actor=actor)
    return request


@transaction.atomic
def decide_advance(*, advance, actor, approve, amount=None, reason=""):
    advance = AdvanceRequest.objects.select_for_update().get(pk=advance.pk)
    if advance.status != AdvanceRequest.Status.REQUESTED:
        raise ValidationError("Advance request is already decided.")
    policy = AdvancePolicy.objects.get(company=advance.company)
    membership = actor.memberships.get(company=advance.company)
    if membership.role not in policy.approver_roles:
        raise ValidationError("Your role cannot approve advances.")
    approved_amount = Decimal(str(amount or advance.requested_amount))
    current_limit = available_advance_limit(advance.worker)
    if approve and approved_amount > min(advance.requested_amount, current_limit):
        raise ValidationError({"amount": "Approved amount exceeds the current limit."})
    advance.status = AdvanceRequest.Status.APPROVED if approve else AdvanceRequest.Status.REJECTED
    advance.approved_amount = approved_amount if approve else 0
    advance.approved_by = actor
    advance.approved_at = timezone.now()
    advance.decision_reason = reason
    advance.save()
    record_audit(instance=advance, action="advance_decided", actor=actor)
    return advance


@transaction.atomic
def mark_disbursed(*, advance, actor, reference, cycle):
    advance = AdvanceRequest.objects.select_for_update().get(pk=advance.pk)
    if advance.status != AdvanceRequest.Status.APPROVED:
        raise ValidationError("Only approved advances can be disbursed.")
    if cycle.company_id != advance.company_id or cycle.status in {
        PayrollCycle.Status.LOCKED,
        PayrollCycle.Status.EXPORTED,
    }:
        raise ValidationError("Choose an unlocked payroll cycle from the same company.")
    advance.status = AdvanceRequest.Status.DISBURSED
    advance.disbursed_at = timezone.now()
    advance.disbursement_reference = reference
    advance.deduction_cycle = cycle
    advance.save()
    record_audit(instance=advance, action="advance_disbursed", actor=actor)
    return advance
