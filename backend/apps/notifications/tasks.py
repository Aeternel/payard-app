from celery import shared_task
from django.utils import timezone

from .models import NotificationOutbox
from .services import deliver_notification


@shared_task
def dispatch_pending_notifications(limit=100):
    ids = list(
        NotificationOutbox.objects.filter(
            status=NotificationOutbox.Status.PENDING,
            scheduled_for__lte=timezone.now(),
        )
        .order_by("scheduled_for")
        .values_list("id", flat=True)[:limit]
    )
    for notification_id in ids:
        deliver_notification_task.delay(str(notification_id))
    return len(ids)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def deliver_notification_task(self, notification_id):
    notification = NotificationOutbox.objects.get(pk=notification_id)
    deliver_notification(notification)
    return notification_id
