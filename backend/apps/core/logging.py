import json
import logging

from django.utils import timezone

from .context import current_request


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        request = current_request.get(None)
        record.request_id = ""
        record.method = ""
        record.path = ""
        record.company_id = ""
        record.user_id = ""
        record.membership_role = ""
        record.remote_addr = ""
        if request is None:
            return True
        record.request_id = str(getattr(request, "request_id", ""))
        record.method = getattr(request, "method", "")
        record.path = getattr(request, "path", "")
        company = getattr(request, "company", None)
        user = getattr(request, "user", None)
        membership = getattr(request, "membership", None)
        record.company_id = str(getattr(company, "id", "") or "")
        record.user_id = str(getattr(user, "id", "") or "")
        record.membership_role = getattr(membership, "role", "")
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        record.remote_addr = (
            forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
        )
        return True


class JSONFormatter(logging.Formatter):
    extra_fields = (
        "event",
        "status_code",
        "duration_ms",
        "request_id",
        "method",
        "path",
        "company_id",
        "user_id",
        "membership_role",
        "remote_addr",
    )

    def format(self, record):
        payload = {
            "time": timezone.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.extra_fields:
            value = getattr(record, field, "")
            if value not in {"", None}:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
