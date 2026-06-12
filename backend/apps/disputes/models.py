from django.db import models

from apps.core.models import TenantModel


class Dispute(TenantModel):
    class Type(models.TextChoices):
        ABSENT_BUT_PRESENT = "absent_but_present", "Absent but present"
        OVERTIME_MISSING = "overtime_missing", "Overtime missing"
        WRONG_DEDUCTION = "wrong_deduction", "Wrong deduction"
        SALARY_NOT_RECEIVED = "salary_not_received", "Salary not received"
        ADVANCE_ISSUE = "advance_issue", "Advance issue"
        WRONG_SITE = "wrong_site", "Wrong site"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SUPERVISOR_REVIEW = "supervisor_review", "Supervisor review"
        HR_REVIEW = "hr_review", "HR review"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.PROTECT, related_name="disputes"
    )
    dispute_type = models.CharField(max_length=40, choices=Type.choices)
    date_reference = models.DateField()
    description = models.TextField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    assigned_to = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    raised_via = models.CharField(max_length=20, default="admin")
    sla_due_at = models.DateTimeField()
    escalated_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_disputes",
    )
    linked_attendance = models.ForeignKey(
        "attendance.AttendanceRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    linked_payroll_line = models.ForeignKey(
        "payroll.PayrollLine", on_delete=models.SET_NULL, null=True, blank=True
    )
    linked_adjustment = models.ForeignKey(
        "payroll.PayrollAdjustment", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "status", "sla_due_at"]),
            models.Index(fields=["company", "worker", "date_reference"]),
        ]


def dispute_evidence_path(instance, filename):
    return f"companies/{instance.company_id}/disputes/{instance.dispute_id}/{filename}"


class DisputeEvidence(TenantModel):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="evidence")
    evidence_type = models.CharField(max_length=20, default="file")
    file = models.FileField(upload_to=dispute_evidence_path, blank=True)
    text = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )


class DisputeComment(TenantModel):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    body = models.TextField()
    is_worker_visible = models.BooleanField(default=True)
