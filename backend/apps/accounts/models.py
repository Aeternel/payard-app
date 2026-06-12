import phonenumbers
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


def normalize_phone(value):
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError("Use an international phone number such as +971501234567.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError("Enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone is required.")
        user = self.model(phone=normalize_phone(phone), **extra_fields)
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel, TimeStampedModel):
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    preferred_language = models.CharField(max_length=10, default="en")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    def clean(self):
        super().clean()
        self.phone = normalize_phone(self.phone)

    def __str__(self):
        return f"{self.name} ({self.phone})"


class Membership(UUIDModel, TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Administrator"
        FINANCE = "finance", "Finance"
        PAYROLL = "payroll", "Payroll"
        HR = "hr", "Human Resources"
        OPERATIONS = "operations", "Operations"
        SUPERVISOR = "supervisor", "Supervisor"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(
        "organizations.Company", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    permission_overrides = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_invitations"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="unique_company_membership")
        ]
        indexes = [models.Index(fields=["company", "role", "is_active"])]


class UserDevice(UUIDModel, TimeStampedModel):
    class Platform(models.TextChoices):
        WEB = "web", "Web"
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    company = models.ForeignKey("organizations.Company", on_delete=models.CASCADE)
    device_id = models.CharField(max_length=255)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    fcm_token = models.TextField(blank=True)
    public_key = models.TextField(blank=True)
    last_seen_at = models.DateTimeField()
    trusted = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company", "device_id"], name="unique_user_company_device"
            )
        ]
