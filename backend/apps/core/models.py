import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(UUIDModel, TimeStampedModel):
    company = models.ForeignKey("organizations.Company", on_delete=models.PROTECT)

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["company", "created_at"])]


class AuditLog(UUIDModel):
    company = models.ForeignKey(
        "organizations.Company", on_delete=models.PROTECT, null=True, blank=True
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    actor_role = models.CharField(max_length=40, blank=True)
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=120, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    request_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "entity_type", "entity_id"]),
            models.Index(fields=["company", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit logs are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit logs cannot be deleted.")


class IdempotencyRecord(UUIDModel):
    company = models.ForeignKey("organizations.Company", on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    endpoint = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_code = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "key", "endpoint"], name="unique_idempotency_request"
            )
        ]

    def __str__(self):
        return f"{self.endpoint}:{self.key}"
