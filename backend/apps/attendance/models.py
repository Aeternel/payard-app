from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel, UUIDModel


class AttendanceRecord(TenantModel):
    class Status(models.TextChoices):
        OPEN = "open", "Checked in"
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LOCKED = "locked", "Payroll locked"

    class VerificationMethod(models.TextChoices):
        QR = "qr", "QR code"
        ID = "id", "Worker ID"
        PHOTO = "photo", "Photo"
        FACE = "face", "Face verification"
        BULK = "bulk", "Bulk supervisor mark"
        MANUAL = "manual", "Manual exception"
        KIOSK = "kiosk", "Kiosk"

    class Source(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE_SYNC = "offline_sync", "Offline sync"
        KIOSK = "kiosk", "Kiosk"
        IMPORT = "import", "Import"

    class Outcome(models.TextChoices):
        FULL_DAY = "full_day", "Full day"
        HALF_DAY = "half_day", "Half day"
        REJECTED = "rejected", "Rejected"

    roster_assignment = models.OneToOneField(
        "sites.RosterAssignment", on_delete=models.PROTECT, related_name="attendance"
    )
    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.PROTECT, related_name="attendance_records"
    )
    site = models.ForeignKey(
        "sites.Site", on_delete=models.PROTECT, related_name="attendance_records"
    )
    shift = models.ForeignKey(
        "sites.ShiftTemplate", on_delete=models.PROTECT, related_name="attendance_records"
    )
    work_date = models.DateField(db_index=True)
    check_in_at = models.DateTimeField()
    check_out_at = models.DateTimeField(null=True, blank=True)
    verification_method = models.CharField(max_length=20, choices=VerificationMethod.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.ONLINE)
    device_id = models.CharField(max_length=255)
    supervisor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="attendance_actions"
    )
    original_captured_at = models.DateTimeField()
    synced_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        default=Outcome.FULL_DAY,
    )
    payable_fraction = models.DecimalField(max_digits=3, decimal_places=2, default=1)
    flags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to="attendance/%Y/%m/%d/", blank=True)
    idempotency_key = models.CharField(max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"], name="unique_attendance_idempotency_key"
            ),
            models.CheckConstraint(
                condition=Q(check_out_at__isnull=True)
                | Q(check_out_at__gte=models.F("check_in_at")),
                name="attendance_checkout_after_checkin",
            ),
            models.CheckConstraint(
                condition=Q(payable_fraction__gte=0) & Q(payable_fraction__lte=1),
                name="attendance_payable_fraction_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "site", "work_date", "status"]),
            models.Index(fields=["company", "worker", "work_date"]),
        ]

    def clean(self):
        if self.roster_assignment_id:
            roster = self.roster_assignment
            if (
                roster.worker_id != self.worker_id
                or roster.site_id != self.site_id
                or roster.shift_id != self.shift_id
                or roster.date != self.work_date
            ):
                raise ValidationError("Attendance must match its roster assignment.")


class AttendanceEvent(UUIDModel):
    attendance = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="events"
    )
    company = models.ForeignKey("organizations.Company", on_delete=models.PROTECT)
    event_type = models.CharField(max_length=40)
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    occurred_at = models.DateTimeField()
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk and AttendanceEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("Attendance events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance events cannot be deleted.")


class AttendanceException(TenantModel):
    class Type(models.TextChoices):
        LATE = "late", "Late arrival"
        EARLY_LEAVE = "early_leave", "Early departure"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RESOLVED = "resolved", "Resolved"

    class Decision(models.TextChoices):
        FULL_DAY = "full_day", "Accept full attendance"
        HALF_DAY = "half_day", "Mark half day"
        REJECTED = "rejected", "Reject attendance"

    attendance = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="exceptions"
    )
    exception_type = models.CharField(max_length=30, choices=Type.choices)
    reason = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    decision = models.CharField(max_length=20, choices=Decision.choices, blank=True)
    decided_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["company", "status", "exception_type"])]


class OvertimeRequest(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    attendance = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="overtime_requests"
    )
    requested_minutes = models.PositiveIntegerField()
    approved_minutes = models.PositiveIntegerField(default=0)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="submitted_overtime"
    )
    decided_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_overtime",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
