import hashlib
import logging
import secrets
from datetime import timedelta

import firebase_admin
import httpx
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.template import Context, Template
from django.utils import timezone
from firebase_admin import credentials, messaging
from rest_framework.exceptions import ValidationError

from apps.accounts.models import UserDevice
from apps.workforce.models import Worker

from .models import (
    DeliveryAttempt,
    NotificationOutbox,
    NotificationTemplate,
    WorkerOTPChallenge,
    WorkerPortalSession,
)

logger = logging.getLogger(__name__)


def enqueue_notification(
    *,
    company,
    channel,
    template_key,
    idempotency_key,
    context=None,
    user=None,
    worker=None,
    destination="",
    language="en",
    scheduled_for=None,
):
    return NotificationOutbox.objects.get_or_create(
        company=company,
        channel=channel,
        idempotency_key=idempotency_key,
        defaults={
            "template_key": template_key,
            "context": context or {},
            "recipient_user": user,
            "recipient_worker": worker,
            "destination": destination,
            "language": language,
            "scheduled_for": scheduled_for or timezone.now(),
        },
    )[0]


def _render(notification):
    template = NotificationTemplate.objects.filter(
        company=notification.company,
        key=notification.template_key,
        channel=notification.channel,
        language=notification.language,
        is_active=True,
    ).first()
    if not template and notification.language != "en":
        template = NotificationTemplate.objects.filter(
            company=notification.company,
            key=notification.template_key,
            channel=notification.channel,
            language="en",
            is_active=True,
        ).first()
    if template:
        return (
            Template(template.subject).render(Context(notification.context)),
            Template(template.body).render(Context(notification.context)),
            template.provider_template_id,
        )
    return (
        notification.subject,
        notification.rendered_body or str(notification.context.get("body", "")),
        "",
    )


def _firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()
    if settings.FIREBASE_PROJECT_ID and settings.FIREBASE_CLIENT_EMAIL:
        private_key = settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n")
        credential = credentials.Certificate(
            {
                "type": "service_account",
                "project_id": settings.FIREBASE_PROJECT_ID,
                "client_email": settings.FIREBASE_CLIENT_EMAIL,
                "private_key": private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
        return firebase_admin.initialize_app(credential)
    return None


def _send_push(notification, subject, body):
    app = _firebase_app()
    if not app:
        raise RuntimeError("Firebase credentials are not configured.")
    tokens = list(
        UserDevice.objects.filter(
            user=notification.recipient_user,
            company=notification.company,
            revoked_at__isnull=True,
        )
        .exclude(fcm_token="")
        .values_list("fcm_token", flat=True)
    )
    if not tokens:
        raise RuntimeError("Recipient has no active Firebase device token.")
    response = messaging.send_each_for_multicast(
        messaging.MulticastMessage(
            notification=messaging.Notification(title=subject, body=body),
            data={key: str(value) for key, value in notification.context.items()},
            tokens=tokens[:500],
        ),
        app=app,
    )
    return {"success_count": response.success_count, "failure_count": response.failure_count}


def _send_whatsapp(notification, body, provider_template_id):
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp credentials are not configured.")
    destination = notification.destination or notification.recipient_worker.phone
    payload = {
        "messaging_product": "whatsapp",
        "to": destination.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    url = (
        f"{settings.WHATSAPP_API_BASE_URL}/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def _send_sms(notification, body):
    destination = notification.destination or notification.recipient_worker.phone
    if settings.SMS_PROVIDER == "console":
        logger.info("SMS to %s: %s", destination, body)
        return {"provider": "console", "accepted": True}
    response = httpx.post(
        settings.SMS_API_URL,
        headers={"Authorization": f"Bearer {settings.SMS_API_KEY}"},
        json={"to": destination, "message": body},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def deliver_notification(notification):
    subject, body, provider_template_id = _render(notification)
    notification.attempts += 1
    notification.status = NotificationOutbox.Status.PROCESSING
    notification.subject = subject
    notification.rendered_body = body
    notification.save(
        update_fields=[
            "attempts",
            "status",
            "subject",
            "rendered_body",
            "updated_at",
        ]
    )
    attempt = DeliveryAttempt.objects.create(
        company=notification.company,
        notification=notification,
        attempt_number=notification.attempts,
        request_payload={"channel": notification.channel, "destination": notification.destination},
    )
    try:
        if notification.channel == NotificationTemplate.Channel.PUSH:
            result = _send_push(notification, subject, body)
        elif notification.channel == NotificationTemplate.Channel.WHATSAPP:
            result = _send_whatsapp(notification, body, provider_template_id)
        elif notification.channel == NotificationTemplate.Channel.SMS:
            result = _send_sms(notification, body)
        else:
            raise RuntimeError(f"Unsupported notification channel: {notification.channel}")
        notification.status = NotificationOutbox.Status.SENT
        notification.sent_at = timezone.now()
        notification.provider_message_id = str(result.get("messages", [{}])[0].get("id", ""))
        notification.last_error = ""
        notification.save()
        attempt.response_payload = result
        attempt.response_status = 200
        attempt.save(update_fields=["response_payload", "response_status", "updated_at"])
    except Exception as exc:
        notification.status = (
            NotificationOutbox.Status.FAILED
            if notification.attempts >= 5
            else NotificationOutbox.Status.PENDING
        )
        notification.last_error = str(exc)[:2000]
        notification.save(update_fields=["status", "last_error", "updated_at"])
        attempt.error = str(exc)[:2000]
        attempt.save(update_fields=["error", "updated_at"])
        raise
    return notification


def create_worker_otp(*, company, phone, request_ip=None):
    worker = Worker.objects.filter(
        company=company, phone=phone, status=Worker.Status.ACTIVE
    ).first()
    # Same response should be returned whether a worker exists to prevent enumeration.
    if not worker:
        return None, None, None
    recent = WorkerOTPChallenge.objects.filter(
        company=company,
        worker=worker,
        created_at__gte=timezone.now() - timedelta(minutes=10),
    ).count()
    if recent >= 3:
        raise ValidationError("Too many OTP requests. Try again later.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = WorkerOTPChallenge.objects.create(
        company=company,
        worker=worker,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=5),
        request_ip=request_ip,
    )
    channel = (
        NotificationTemplate.Channel.SMS
        if (
            worker.notification_channel == Worker.NotificationChannel.SMS
            or not settings.WHATSAPP_ACCESS_TOKEN
            or not settings.WHATSAPP_PHONE_NUMBER_ID
        )
        else NotificationTemplate.Channel.WHATSAPP
    )
    notification = enqueue_notification(
        company=company,
        channel=channel,
        template_key="worker_otp",
        idempotency_key=f"worker-otp-{challenge.id}",
        worker=worker,
        language=worker.preferred_language,
        context={
            "code": code,
            "body": f"Your PayYard verification code is {code}. It expires in 5 minutes.",
        },
    )
    return challenge, notification, code


def verify_worker_otp(*, challenge_id, code, ip_address=None, user_agent=""):
    challenge = (
        WorkerOTPChallenge.objects.select_related("worker", "company")
        .filter(pk=challenge_id, consumed_at__isnull=True)
        .first()
    )
    if not challenge or challenge.expires_at <= timezone.now() or challenge.attempts >= 5:
        raise ValidationError("OTP is invalid or expired.")
    challenge.attempts += 1
    if not check_password(code, challenge.code_hash):
        challenge.save(update_fields=["attempts", "updated_at"])
        raise ValidationError("OTP is invalid or expired.")
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["attempts", "consumed_at", "updated_at"])
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    WorkerPortalSession.objects.create(
        company=challenge.company,
        worker=challenge.worker,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(hours=12),
        last_seen_at=timezone.now(),
        ip_address=ip_address,
        user_agent=user_agent[:500],
    )
    return raw_token, challenge.worker
