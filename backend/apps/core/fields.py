import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _derived_key():
    return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())


def _fernet():
    configured = settings.FIELD_ENCRYPTION_KEY
    if configured:
        try:
            return Fernet(configured.encode())
        except ValueError:
            if settings.ENVIRONMENT in {"development", "local", "test"}:
                return Fernet(_derived_key())
            raise ValueError(
                "FIELD_ENCRYPTION_KEY must be a valid Fernet key: 32 url-safe base64-encoded bytes."
            )
    key = _derived_key()
    return Fernet(key)


class EncryptedTextField(models.TextField):
    prefix = "enc::"

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if value is None or not isinstance(value, str) or not value.startswith(self.prefix):
            return value
        try:
            return _fernet().decrypt(value.removeprefix(self.prefix).encode()).decode()
        except InvalidToken:
            return value

    def get_prep_value(self, value):
        if value is None or value == "" or str(value).startswith(self.prefix):
            return value
        encrypted = _fernet().encrypt(str(value).encode()).decode()
        return f"{self.prefix}{encrypted}"
