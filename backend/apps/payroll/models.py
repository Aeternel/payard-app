from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel


class WageRule(TenantModel):
    name = models.CharField(max_length=120)
    priority = models.PositiveSmallIntegerField(default=100)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    worker = models.ForeignKey("workforce.Worker", on_delete=models.CASCADE, null=True, blank=True)
    site = models.ForeignKey("sites.Site", on_delete=models.CASCADE, null=True, blank=True)
    configuration = models.JSONField(
        default=dict,
        help_text="Versioned wage rule configuration evaluated by the wage service.",
    )
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "-effective_from"]
        indexes = [models.Index(fields=["company", "is_active", "effective_from"])]


class DailyWageLedger(TenantModel):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", "Provisional"
        FINAL = "final", "Final"
        ADJUSTED = "adjusted", "Adjusted"

    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.PROTECT, related_name="wage_ledgers"
    )
    attendance = models.OneToOneField(
        "attendance.AttendanceRecord", on_delete=models.PROTECT, related_name="wage_ledger"
    )
    work_date = models.DateField(db_index=True)
    regular_minutes = models.PositiveIntegerField(default=0)
    overtime_minutes = models.PositiveIntegerField(default=0)
    regular_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_estimate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_estimate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculation_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROVISIONAL)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "work_date"], name="unique_daily_worker_wage_ledger"
            ),
            models.CheckConstraint(
                condition=Q(net_estimate__gte=0), name="daily_wage_net_nonnegative"
            ),
        ]
        indexes = [models.Index(fields=["company", "work_date", "status"])]


class PayrollCycle(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "In review"
        APPROVED = "approved", "Finance approved"
        LOCKED = "locked", "Locked"
        EXPORTED = "exported", "Exported"
        PAID = "paid", "Paid"

    name = models.CharField(max_length=80)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    readiness_snapshot = models.JSONField(default=dict, blank=True)
    submitted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_payroll_cycles",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_payroll_cycles",
    )
    locked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_payroll_cycles",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "period_start", "period_end", "version"],
                name="unique_payroll_cycle_version",
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="payroll_period_dates_valid",
            ),
        ]
        ordering = ["-period_start", "-version"]


class PayrollLine(TenantModel):
    cycle = models.ForeignKey(PayrollCycle, on_delete=models.PROTECT, related_name="lines")
    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.PROTECT, related_name="payroll_lines"
    )
    contract_basic = models.DecimalField(max_digits=12, decimal_places=2)
    regular_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    absence_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    manual_net_pay = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    manual_override_reason = models.TextField(blank=True)
    manual_override_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_line_overrides",
    )
    manual_override_at = models.DateTimeField(null=True, blank=True)
    flags = models.JSONField(default=list, blank=True)
    calculation_snapshot = models.JSONField(default=dict)
    employer_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cycle", "worker"], name="unique_cycle_worker_line"),
            models.CheckConstraint(
                condition=Q(net_pay__gte=Decimal("0")), name="payroll_line_net_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(manual_net_pay__isnull=True)
                | Q(manual_net_pay__gte=Decimal("0")),
                name="payroll_line_manual_net_nonnegative",
            ),
        ]


class PayrollAdjustment(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        APPLIED = "applied", "Applied to next cycle"

    cycle = models.ForeignKey(PayrollCycle, on_delete=models.PROTECT, related_name="adjustments")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.PROTECT)
    source_type = models.CharField(max_length=50)
    source_id = models.UUIDField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="requested_adjustments"
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_adjustments",
    )
    applied_cycle = models.ForeignKey(
        PayrollCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_adjustments",
    )


def payroll_export_path(instance, filename):
    return (
        f"companies/{instance.company_id}/payroll/"
        f"{instance.cycle_id}/v{instance.version}/{filename}"
    )


class PayrollExport(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    cycle = models.ForeignKey(PayrollCycle, on_delete=models.PROTECT, related_name="exports")
    export_type = models.CharField(max_length=30, default="wps")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    file = models.FileField(upload_to=payroll_export_path, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "export_type", "version"], name="unique_payroll_export_version"
            )
        ]
