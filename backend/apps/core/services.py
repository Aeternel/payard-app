import dataclasses
import hashlib
import json
from decimal import Decimal
from enum import Enum
from uuid import UUID

from django.db import models
from django.db.models.fields.files import FieldFile

from .context import current_request
from .fields import EncryptedTextField
from .models import AuditLog


def json_safe(value):
    if isinstance(value, FieldFile):
        return value.name or ""
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def model_snapshot(instance: models.Model) -> dict:
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in {"password"}:
            continue
        if isinstance(field, EncryptedTextField):
            data[field.name] = "[REDACTED]"
        else:
            data[field.name] = json_safe(getattr(instance, field.attname))
    return data


def record_audit(*, instance, action, actor=None, before=None, after=None, metadata=None):
    request = current_request.get()
    company = getattr(instance, "company", None)
    if company is None and instance.__class__.__name__ == "Company":
        company = instance
    role = ""
    if actor and company:
        membership = actor.memberships.filter(company=company, is_active=True).first()
        role = membership.role if membership else ""
    return AuditLog.objects.create(
        company=company,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_role=role,
        action=action,
        entity_type=instance._meta.label_lower,
        entity_id=str(instance.pk),
        before=before or {},
        after=after or model_snapshot(instance),
        metadata=metadata or {},
        ip_address=_client_ip(request),
        device_id=request.headers.get("X-Device-ID", "") if request else "",
        request_id=getattr(request, "request_id", None),
    )


def stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=json_safe).encode()
    return hashlib.sha256(encoded).hexdigest()


def _client_ip(request):
    if not request:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
