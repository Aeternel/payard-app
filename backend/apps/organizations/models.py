from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import TenantModel, TimeStampedModel, UUIDModel


class Company(UUIDModel, TimeStampedModel):
    class PayrollFrequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        FOUR_WEEKLY = "four_weekly", "Every four weeks"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    legal_name = models.CharField(max_length=255)
    trade_license_number = EncryptedTextField(blank=True)
    mohre_establishment_number = EncryptedTextField(blank=True)
    emirate = models.CharField(max_length=30, blank=True)
    industry = models.CharField(max_length=80, blank=True)
    timezone = models.CharField(max_length=50, default="Asia/Dubai")
    currency = models.CharField(max_length=3, default="AED")
    payroll_frequency = models.CharField(
        max_length=20, choices=PayrollFrequency.choices, default=PayrollFrequency.MONTHLY
    )
    payroll_cutoff_day = models.PositiveSmallIntegerField(
        default=25, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


class CompanyPolicy(TenantModel):
    company = models.OneToOneField(Company, on_delete=models.PROTECT, related_name="policy")
    half_day_deduction_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of a normal day's pay deducted for a half-day decision.",
    )
    normal_daily_hours = models.DecimalField(max_digits=4, decimal_places=2, default=8)
    normal_weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, default=48)
    max_consecutive_hours = models.DecimalField(max_digits=4, decimal_places=2, default=5)
    minimum_break_minutes = models.PositiveSmallIntegerField(default=60)
    overtime_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.25)
    night_overtime_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.50)
    night_period_start = models.TimeField(default="22:00")
    night_period_end = models.TimeField(default="04:00")
    weekly_rest_days = models.PositiveSmallIntegerField(default=1)
    ramadan_enabled = models.BooleanField(default=True)
    ramadan_daily_reduction_hours = models.DecimalField(max_digits=4, decimal_places=2, default=2)
    ramadan_start = models.DateField(null=True, blank=True)
    ramadan_end = models.DateField(null=True, blank=True)
    midday_break_enabled = models.BooleanField(default=True)
    midday_break_start_date = models.CharField(max_length=5, default="06-15")
    midday_break_end_date = models.CharField(max_length=5, default="09-15")
    midday_break_start_time = models.TimeField(default="12:30")
    midday_break_end_time = models.TimeField(default="15:00")
    require_attendance_photo = models.BooleanField(default=False)
    require_biometric_consent = models.BooleanField(default=True)
    allow_manual_attendance = models.BooleanField(default=True)
    attendance_edit_window_hours = models.PositiveSmallIntegerField(default=48)
    data_retention = models.JSONField(
        default=dict,
        blank=True,
        help_text="Retention periods in days by data category.",
    )


class WPSConfiguration(TenantModel):
    company = models.OneToOneField(
        Company, on_delete=models.PROTECT, related_name="wps_configuration"
    )
    partner_name = models.CharField(max_length=150, blank=True)
    employer_bank_routing_code = EncryptedTextField(blank=True)
    employer_account = EncryptedTextField(blank=True)
    employer_reference = EncryptedTextField(blank=True)
    file_format = models.CharField(max_length=40, default="generic_sif")
    field_mapping = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)


class FeatureFlag(TenantModel):
    key = models.SlugField(max_length=80)
    enabled = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "key"], name="unique_company_feature")
        ]
