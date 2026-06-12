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
        if not settings.WHATSAPP_APP_SECRET:
            findings.append(
                Warning(
                    "WHATSAPP_APP_SECRET is empty; inbound webhooks cannot be verified.",
                    id="payyard.W001",
                )
            )
    return findings
