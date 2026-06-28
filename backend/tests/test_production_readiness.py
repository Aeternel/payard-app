import base64

import pytest
from django.core.checks import Tags, run_checks
from django.test import override_settings


FERNET_TEST_KEY = base64.urlsafe_b64encode(b"0" * 32).decode()


@pytest.mark.django_db
def test_readiness_endpoint_reports_database_and_cache(api_client):
    response = api_client.get("/ready/")

    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert response.data["checks"]["database"]["status"] == "ok"
    assert response.data["checks"]["cache"]["status"] == "ok"


@pytest.mark.django_db
@override_settings(ENABLE_API_DOCS=False)
def test_api_docs_are_hidden_when_disabled(api_client):
    schema_response = api_client.get("/api/schema/")
    docs_response = api_client.get("/api/docs/")

    assert schema_response.status_code == 404
    assert docs_response.status_code == 404


@override_settings(
    ENVIRONMENT="production",
    DEBUG=False,
    SECRET_KEY="s" * 60,
    FIELD_ENCRYPTION_KEY=FERNET_TEST_KEY,
    ALLOWED_HOSTS=["localhost"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_HSTS_SECONDS=31536000,
    CELERY_BROKER_URL="amqp://guest:guest@localhost:5672//",
    CSRF_TRUSTED_ORIGINS=["https://app.example.com"],
    CORS_ALLOWED_ORIGINS=["https://app.example.com"],
    ENABLE_API_DOCS=False,
    ENABLE_ADMIN=False,
    WHATSAPP_APP_SECRET="configured",
)
def test_deploy_checks_reject_local_defaults():
    findings = run_checks(tags=[Tags.security], deploy=True)
    finding_ids = {finding.id for finding in findings}

    assert "payyard.E004" in finding_ids
    assert "payyard.E005" in finding_ids
    assert "payyard.E009" in finding_ids
    assert "payyard.E010" in finding_ids


@override_settings(
    ENVIRONMENT="production",
    DEBUG=False,
    SECRET_KEY="s" * 60,
    FIELD_ENCRYPTION_KEY=FERNET_TEST_KEY,
    ALLOWED_HOSTS=["api.example.com"],
    DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "payyard"}},
    CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_HSTS_SECONDS=31536000,
    CELERY_BROKER_URL="amqp://payyard:secret@mq:5672/payyard",
    CSRF_TRUSTED_ORIGINS=["https://app.example.com"],
    CORS_ALLOWED_ORIGINS=["https://app.example.com"],
    ENABLE_API_DOCS=True,
    ENABLE_ADMIN=True,
    WHATSAPP_APP_SECRET="configured",
)
def test_deploy_checks_warn_when_docs_or_admin_are_enabled():
    findings = run_checks(tags=[Tags.security], deploy=True)
    finding_ids = {finding.id for finding in findings}

    assert "payyard.W004" in finding_ids
    assert "payyard.W005" in finding_ids
