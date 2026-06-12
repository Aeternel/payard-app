from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TenantModel


class Site(TenantModel):
    class Environment(models.TextChoices):
        INDOOR = "indoor", "Indoor"
        OUTDOOR = "outdoor", "Outdoor"
        MIXED = "mixed", "Mixed"
        EXEMPT_OUTDOOR = "exempt_outdoor", "Outdoor exempt activity"

    name = models.CharField(max_length=150)
    client_name = models.CharField(max_length=150, blank=True)
    address = models.TextField(blank=True)
    environment = models.CharField(
        max_length=30, choices=Environment.choices, default=Environment.INDOOR
    )
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_company_site")
        ]

    def __str__(self):
        return self.name


class SiteSupervisor(TenantModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="supervisor_links")
    supervisor = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="site_links"
    )
    is_primary = models.BooleanField(default=False)
    active_from = models.DateField()
    active_until = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "supervisor"], name="unique_site_supervisor")
        ]


class ShiftTemplate(TenantModel):
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveSmallIntegerField(default=60)
    auto_break = models.BooleanField(default=True)
    is_night_shift = models.BooleanField(default=False)
    shift_worker_exempt_from_night_premium = models.BooleanField(default=False)
    weekly_off_day = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(6)]
    )
    ramadan_override_hours = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="unique_company_shift_template"
            )
        ]

    @property
    def crosses_midnight(self):
        return self.end_time <= self.start_time


class RosterAssignment(TenantModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        REPLACED = "replaced", "Replaced"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.PROTECT, related_name="roster_assignments"
    )
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="roster_assignments")
    shift = models.ForeignKey(
        ShiftTemplate, on_delete=models.PROTECT, related_name="roster_assignments"
    )
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    replacement_for = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replacements"
    )
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "date"], name="one_roster_assignment_per_worker_day"
            )
        ]
        indexes = [models.Index(fields=["company", "site", "date", "status"])]

    def clean(self):
        for obj in (self.worker, self.site, self.shift):
            if obj and obj.company_id != self.company_id:
                raise ValidationError("Roster references must belong to the same company.")


class WorkerTransfer(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    worker = models.ForeignKey("workforce.Worker", on_delete=models.PROTECT)
    from_assignment = models.ForeignKey(
        RosterAssignment, on_delete=models.PROTECT, related_name="outgoing_transfers"
    )
    to_site = models.ForeignKey(Site, on_delete=models.PROTECT)
    to_shift = models.ForeignKey(ShiftTemplate, on_delete=models.PROTECT)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="requested_transfers"
    )
    decided_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_transfers",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
