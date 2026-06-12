import hashlib

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import WorkerPortalSession


class WorkerPortalAuthentication(BaseAuthentication):
    keyword = "Worker"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} "):
            return None
        raw = header.removeprefix(f"{self.keyword} ").strip()
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        session = (
            WorkerPortalSession.objects.select_related("worker", "company")
            .filter(
                token_hash=token_hash,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            .first()
        )
        if not session:
            raise AuthenticationFailed("Worker session is invalid or expired.")
        session.last_seen_at = timezone.now()
        session.save(update_fields=["last_seen_at", "updated_at"])
        request.worker = session.worker
        request.company = session.company
        return session.worker, session
