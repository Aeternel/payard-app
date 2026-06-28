import logging
import time
import uuid

from .context import current_request

logger = logging.getLogger("payyard.request")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.monotonic()
        request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = current_request.set(request)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request.request_id
            logger.info(
                "Request completed",
                extra={
                    "event": "request.completed",
                    "status_code": response.status_code,
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                },
            )
            return response
        finally:
            current_request.reset(token)
