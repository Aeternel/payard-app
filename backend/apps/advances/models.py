from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.fields import EncryptedTextField
from apps.core.models import TenantModel


def default_advance_approver_roles():
    return ["finance", "owner"]


class AdvancePolicy(TenantModel):
    enabled = models.BooleanField(default=True)
    minimum_service_days = models.PositiveIntegerField(default=30)
    max_earned_wage_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    max_requests_per_cycle = models.PositiveSmallIntegerField(default=1)
    minimum_amount = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    maximum_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    approver_roles = models.JSONField(default=default_advance_approver_roles)
    acknowledgement_text = models.TextField(
        default="I understand this amount will be deducted from my payroll."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company"], name="one_advance_policy_per_company")
        ]


class AdvanceRequest(TenantModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DISBURSED = "disbursed", "Disbursed"
        DEDUCTED = "deducted", "Deducted"
        CANCELLED = "cancelled", "Cancelled"

    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.PROTECT, related_name="advance_requests"
    )
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    available_limit_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    acknowledgement = models.BooleanField(default=False)
    acknowledgement_text = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    requested_via = models.CharField(max_length=20, default="admin")
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_advances",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    disbursement_reference = EncryptedTextField(blank=True)
    deduction_cycle = models.ForeignKey(
        "payroll.PayrollCycle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advance_requests",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_amount__gt=Decimal("0")),
                name="advance_requested_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(approved_amount__gte=Decimal("0")),
                name="advance_approved_amount_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=["company", "worker", "status"])]
