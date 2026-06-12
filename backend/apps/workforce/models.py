from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.fields import EncryptedTextField
from apps.core.models import TenantModel


class Worker(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    class WageType(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        DAILY = "daily", "Daily"
        HOURLY = "hourly", "Hourly"
        SHIFT = "shift", "Per shift"

    class NotificationChannel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"
        BOTH = "both", "Both"
        NONE = "none", "None"

    class EmploymentCategory(models.TextChoices):
        SITE_WORKER = "site_worker", "Site worker"
        STAFF = "staff", "Staff employee"

    user_account = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_profile",
        help_text="Optional login account linked to this employee's payroll identity.",
    )
    employment_category = models.CharField(
        max_length=20,
        choices=EmploymentCategory.choices,
        default=EmploymentCategory.SITE_WORKER,
    )
    department = models.CharField(max_length=100, blank=True)
    worker_code = models.CharField(max_length=40)
    full_name = models.CharField(max_length=180)
    phone = models.CharField(max_length=20, blank=True)
    nationality = models.CharField(max_length=80, blank=True)
    preferred_language = models.CharField(max_length=10, default="en")
    notification_channel = models.CharField(
        max_length=12,
        choices=NotificationChannel.choices,
        default=NotificationChannel.WHATSAPP,
    )
    job_title = models.CharField(max_length=100, blank=True)
    employment_start_date = models.DateField()
    employment_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    wage_type = models.CharField(max_length=20, choices=WageType.choices)
    basic_wage = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    allowances = models.JSONField(default=list, blank=True)
    payroll_method = models.CharField(max_length=40, blank=True)
    bank_routing_code = EncryptedTextField(blank=True)
    bank_account_or_card = EncryptedTextField(blank=True)
    default_site = models.ForeignKey(
        "sites.Site",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_workers",
    )
    supervisor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_workers",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["worker_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "worker_code"], name="unique_company_worker_code"
            ),
            models.CheckConstraint(
                condition=Q(basic_wage__gte=0), name="worker_basic_wage_nonnegative"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "phone"]),
        ]

    @property
    def payroll_ready(self):
        return bool(self.basic_wage > 0 and self.payroll_method and self.bank_account_or_card)

    def __str__(self):
        return f"{self.worker_code} - {self.full_name}"

    @property
    def is_authenticated(self):
        return True


def worker_document_path(instance, filename):
    return f"companies/{instance.company_id}/workers/{instance.worker_id}/documents/{filename}"


class WorkerDocument(TenantModel):
    class Type(models.TextChoices):
        EMIRATES_ID = "emirates_id", "Emirates ID"
        PASSPORT = "passport", "Passport"
        WORK_PERMIT = "work_permit", "Work permit"
        CONTRACT = "contract", "Employment contract"
        OTHER = "other", "Other"

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=Type.choices)
    reference_number = EncryptedTextField(blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    file = models.FileField(upload_to=worker_document_path, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, default="pending")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "document_type", "reference_number"],
                name="unique_worker_document",
            )
        ]


class ConsentRecord(TenantModel):
    class ConsentType(models.TextChoices):
        PRIVACY = "privacy", "Privacy notice"
        PHOTO = "photo", "Photo attendance"
        BIOMETRIC = "biometric", "Biometric processing"
        LOCATION = "location", "Location processing"
        NOTIFICATIONS = "notifications", "Worker notifications"

    class Status(models.TextChoices):
        GRANTED = "granted", "Granted"
        WITHDRAWN = "withdrawn", "Withdrawn"
        DECLINED = "declined", "Declined"

    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="consents")
    consent_type = models.CharField(max_length=30, choices=ConsentType.choices)
    version = models.CharField(max_length=30)
    language = models.CharField(max_length=10)
    channel = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices)
    captured_at = models.DateTimeField()
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    captured_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-captured_at"]
        indexes = [models.Index(fields=["worker", "consent_type", "captured_at"])]
