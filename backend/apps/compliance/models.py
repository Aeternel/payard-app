from django.db import models

from apps.core.models import TenantModel


class ComplianceAlert(TenantModel):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    alert_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    title = models.CharField(max_length=180)
    description = models.TextField()
    entity_type = models.CharField(max_length=80)
    entity_id = models.UUIDField()
    occurrence_date = models.DateField()
    unique_key = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    metadata = models.JSONField(default=dict, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "unique_key"], name="unique_company_compliance_alert"
            )
        ]
        indexes = [models.Index(fields=["company", "status", "severity"])]
