from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def production_security_checks(app_configs, **kwargs):
    findings = []
    if settings.ENVIRONMENT in {"staging", "production"}:
        if not settings.FIELD_ENCRYPTION_KEY:
            findings.append(
                Error(
                    "FIELD_ENCRYPTION_KEY is required outside development.",
                    id="payyard.E001",
                )
            )
        if len(settings.SECRET_KEY) < 50 or "change" in settings.SECRET_KEY.lower():
            findings.append(Error("SECRET_KEY is not suitable for deployment.", id="payyard.E002"))
        if settings.DEBUG:
            findings.append(Error("DEBUG must be false for deployment.", id="payyard.E003"))
        database_engine = settings.DATABASES["default"]["ENGINE"]
        if database_engine == "django.db.backends.sqlite3":
            findings.append(
                Error(
                    "SQLite is not suitable for staging or production deployments.",
                    id="payyard.E004",
                )
            )
        if "*" in settings.ALLOWED_HOSTS or _only_local_hosts(settings.ALLOWED_HOSTS):
            findings.append(
                Error(
                    "ALLOWED_HOSTS must be set to real deployment hostnames.",
                    id="payyard.E005",
                )
            )
        if not settings.SECURE_SSL_REDIRECT:
            findings.append(Error("SECURE_SSL_REDIRECT must be enabled.", id="payyard.E006"))
        if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
            findings.append(
                Error(
                    "Session and CSRF cookies must be marked secure.",
                    id="payyard.E007",
                )
            )
        if settings.SECURE_HSTS_SECONDS < 31536000:
            findings.append(
                Error(
                    "SECURE_HSTS_SECONDS must be at least one year in production.",
                    id="payyard.E008",
                )
            )
        if settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache":
            findings.append(
                Error(
                    "Shared cache infrastructure is required outside development.",
                    id="payyard.E009",
                )
            )
        if settings.CELERY_BROKER_URL.startswith("amqp://guest:guest@localhost:5672//"):
            findings.append(
                Error(
                    "CELERY_BROKER_URL is still using the insecure local default.",
                    id="payyard.E010",
                )
            )
        if not settings.CSRF_TRUSTED_ORIGINS:
            findings.append(
                Error(
                    "CSRF_TRUSTED_ORIGINS must include the frontend origin.",
                    id="payyard.E011",
                )
            )
        for origin in settings.CSRF_TRUSTED_ORIGINS:
            if not _is_secure_origin(origin):
                findings.append(
                    Warning(
                        f"CSRF trusted origin '{origin}' is not HTTPS.",
                        id="payyard.W002",
                    )
                )
        for origin in settings.CORS_ALLOWED_ORIGINS:
            if not _is_secure_origin(origin):
                findings.append(
                    Warning(
                        f"CORS origin '{origin}' is not HTTPS.",
                        id="payyard.W003",
                    )
                )
        if settings.ENABLE_API_DOCS:
            findings.append(
                Warning(
                    "API docs are enabled in a deployment environment.",
                    id="payyard.W004",
                )
            )
        if settings.ENABLE_ADMIN:
            findings.append(
                Warning(
                    "Django admin is enabled in a deployment environment.",
                    id="payyard.W005",
                )
            )
        if not settings.WHATSAPP_APP_SECRET:
            findings.append(
                Warning(
                    "WHATSAPP_APP_SECRET is empty; inbound webhooks cannot be verified.",
                    id="payyard.W001",
                )
            )
    return findings


def _only_local_hosts(hosts):
    local_hosts = {"localhost", "127.0.0.1", "backend"}
    return not hosts or all(host in local_hosts for host in hosts)


def _is_secure_origin(origin):
    parsed = urlparse(origin)
    if parsed.hostname in {"localhost", "127.0.0.1"}:
        return True
    return parsed.scheme == "https"
