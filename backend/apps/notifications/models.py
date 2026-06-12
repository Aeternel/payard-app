from django.db import models

from apps.core.models import TenantModel


class NotificationTemplate(TenantModel):
    class Channel(models.TextChoices):
        PUSH = "push", "Firebase push"
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"

    key = models.SlugField(max_length=80)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    language = models.CharField(max_length=10, default="en")
    subject = models.CharField(max_length=180, blank=True)
    body = models.TextField()
    provider_template_id = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "key", "channel", "language"],
                name="unique_notification_template",
            )
        ]


class NotificationOutbox(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    channel = models.CharField(max_length=20, choices=NotificationTemplate.Channel.choices)
    template_key = models.CharField(max_length=80)
    language = models.CharField(max_length=10, default="en")
    recipient_user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True
    )
    recipient_worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.CASCADE, null=True, blank=True
    )
    destination = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=180, blank=True)
    rendered_body = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=128)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    scheduled_for = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key", "channel"],
                name="unique_notification_idempotency",
            )
        ]
        indexes = [models.Index(fields=["status", "scheduled_for"])]


class DeliveryAttempt(TenantModel):
    notification = models.ForeignKey(
        NotificationOutbox, on_delete=models.CASCADE, related_name="delivery_attempts"
    )
    attempt_number = models.PositiveSmallIntegerField()
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)


class WorkerOTPChallenge(TenantModel):
    worker = models.ForeignKey("workforce.Worker", on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["worker", "expires_at", "consumed_at"])]


class WorkerPortalSession(TenantModel):
    worker = models.ForeignKey(
        "workforce.Worker", on_delete=models.CASCADE, related_name="portal_sessions"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)


class WhatsAppWebhookEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()
    signature_valid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="received")
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.event_id
