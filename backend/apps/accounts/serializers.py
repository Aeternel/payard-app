from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.services import record_audit
from apps.workforce.models import Worker

from .models import Membership, User, UserDevice, normalize_phone


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "name", "email", "preferred_language", "is_active"]
        read_only_fields = ["id"]
        extra_kwargs = {"password": {"write_only": True}}


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    payroll_profile_id = serializers.SerializerMethodField()
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=User.objects.all(), write_only=True
    )

    class Meta:
        model = Membership
        fields = [
            "id",
            "user",
            "user_id",
            "role",
            "payroll_profile_id",
            "permission_overrides",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_payroll_profile_id(self, obj):
        profile = getattr(obj.user, "payroll_profile", None)
        return str(profile.id) if profile and profile.company_id == obj.company_id else None

    def validate_role(self, value):
        request = self.context.get("request")
        if (
            request
            and request.membership.role != Membership.Role.OWNER
            and value in {Membership.Role.OWNER, Membership.Role.ADMIN}
        ):
            raise serializers.ValidationError(
                "Only an owner can grant owner or admin access."
            )
        return value


class StaffOnboardingSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    preferred_language = serializers.CharField(max_length=10, default="en")
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    temporary_password = serializers.CharField(write_only=True, min_length=12)
    create_payroll_profile = serializers.BooleanField(default=True)
    worker_code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True)
    employment_start_date = serializers.DateField(required=False)
    basic_wage = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )
    allowances = serializers.JSONField(default=list)
    payroll_method = serializers.CharField(max_length=40, required=False, allow_blank=True)
    bank_routing_code = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )
    bank_account_or_card = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )

    def validate_phone(self, value):
        phone = normalize_phone(value)
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("A login account already uses this phone number.")
        return phone

    def validate_temporary_password(self, value):
        validate_password(value)
        return value

    def validate_role(self, value):
        actor_role = self.context["request"].membership.role
        if actor_role != Membership.Role.OWNER and value in {
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        }:
            raise serializers.ValidationError("Only an owner can grant owner or admin access.")
        return value

    def validate(self, attrs):
        if attrs["create_payroll_profile"]:
            required = ["worker_code", "employment_start_date", "basic_wage"]
            errors = {
                field: "Required when creating a payroll profile."
                for field in required
                if attrs.get(field) in {None, ""}
            }
            if attrs.get("basic_wage") is not None and attrs["basic_wage"] <= 0:
                errors["basic_wage"] = "Staff basic wage must be greater than zero."
            worker_code = attrs.get("worker_code", "").strip()
            if worker_code and Worker.objects.filter(
                company=self.context["request"].company,
                worker_code__iexact=worker_code,
            ).exists():
                errors["worker_code"] = "This employee code is already in use."
            if errors:
                raise serializers.ValidationError(errors)
            attrs["worker_code"] = worker_code
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        payroll_fields = {
            key: validated_data.pop(key, None)
            for key in [
                "worker_code",
                "department",
                "job_title",
                "employment_start_date",
                "basic_wage",
                "allowances",
                "payroll_method",
                "bank_routing_code",
                "bank_account_or_card",
            ]
        }
        create_payroll_profile = validated_data.pop("create_payroll_profile")
        role = validated_data.pop("role")
        password = validated_data.pop("temporary_password")
        user = User.objects.create_user(password=password, **validated_data)
        membership = Membership.objects.create(
            user=user,
            company=request.company,
            role=role,
            invited_by=request.user,
        )
        if create_payroll_profile:
            Worker.objects.create(
                company=request.company,
                user_account=user,
                employment_category=Worker.EmploymentCategory.STAFF,
                worker_code=payroll_fields["worker_code"],
                full_name=user.name,
                phone=user.phone,
                preferred_language=user.preferred_language,
                notification_channel=Worker.NotificationChannel.WHATSAPP,
                department=payroll_fields.get("department") or "",
                job_title=payroll_fields.get("job_title")
                or Membership.Role(role).label,
                employment_start_date=payroll_fields["employment_start_date"],
                status=Worker.Status.ACTIVE,
                wage_type=Worker.WageType.MONTHLY,
                basic_wage=payroll_fields["basic_wage"],
                allowances=payroll_fields.get("allowances") or [],
                payroll_method=payroll_fields.get("payroll_method") or "",
                bank_routing_code=payroll_fields.get("bank_routing_code") or "",
                bank_account_or_card=payroll_fields.get("bank_account_or_card") or "",
            )
        record_audit(instance=membership, action="staff_onboarded", actor=request.user)
        return membership


class StaffPayrollProfileSerializer(serializers.Serializer):
    worker_code = serializers.CharField(max_length=40)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True)
    employment_start_date = serializers.DateField()
    basic_wage = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    allowances = serializers.JSONField(default=list)
    payroll_method = serializers.CharField(max_length=40, required=False, allow_blank=True)
    bank_routing_code = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )
    bank_account_or_card = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )

    def validate_worker_code(self, value):
        worker_code = value.strip()
        if Worker.objects.filter(
            company=self.context["request"].company,
            worker_code__iexact=worker_code,
        ).exists():
            raise serializers.ValidationError("This employee code is already in use.")
        return worker_code

    def validate(self, attrs):
        membership = self.context["membership"]
        profile = getattr(membership.user, "payroll_profile", None)
        if profile:
            raise serializers.ValidationError(
                "This account already has a payroll profile."
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        membership = self.context["membership"]
        user = membership.user
        profile = Worker.objects.create(
            company=request.company,
            user_account=user,
            employment_category=Worker.EmploymentCategory.STAFF,
            worker_code=validated_data["worker_code"],
            full_name=user.name,
            phone=user.phone,
            preferred_language=user.preferred_language,
            notification_channel=Worker.NotificationChannel.WHATSAPP,
            department=validated_data.get("department", ""),
            job_title=validated_data.get("job_title") or membership.get_role_display(),
            employment_start_date=validated_data["employment_start_date"],
            status=Worker.Status.ACTIVE,
            wage_type=Worker.WageType.MONTHLY,
            basic_wage=validated_data["basic_wage"],
            allowances=validated_data.get("allowances", []),
            payroll_method=validated_data.get("payroll_method", ""),
            bank_routing_code=validated_data.get("bank_routing_code", ""),
            bank_account_or_card=validated_data.get("bank_account_or_card", ""),
        )
        record_audit(
            instance=profile,
            action="staff_payroll_profile_linked",
            actor=request.user,
        )
        return profile


class CompanyTokenSerializer(TokenObtainPairSerializer):
    username_field = "phone"

    def validate(self, attrs):
        phone = normalize_phone(attrs.get("phone"))
        user = authenticate(
            request=self.context.get("request"), phone=phone, password=attrs.get("password")
        )
        if not user:
            raise serializers.ValidationError("Invalid phone or password.")
        memberships = list(
            user.memberships.select_related("company")
            .filter(company__is_active=True, is_active=True)
            .order_by("created_at")[:2]
        )
        if not memberships:
            raise serializers.ValidationError("Your account has no active company access.")
        if len(memberships) > 1:
            raise serializers.ValidationError(
                "Your account has multiple active company memberships. "
                "Contact an administrator to keep one active login membership."
            )
        membership = memberships[0]

        refresh = RefreshToken.for_user(user)
        refresh["company_id"] = str(membership.company_id)
        refresh["company_slug"] = membership.company.slug
        refresh["role"] = membership.role
        request = self.context.get("request")
        user.last_login_ip = request.META.get("REMOTE_ADDR") if request else None
        user.last_login = timezone.now()
        user.save(update_fields=["last_login_ip", "last_login", "updated_at"])
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
            "company": {
                "id": str(membership.company_id),
                "name": membership.company.name,
                "slug": membership.company.slug,
            },
            "role": membership.role,
        }


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=12)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.password_changed_at = timezone.now()
        user.save(update_fields=["password", "password_changed_at", "updated_at"])
        record_audit(instance=user, action="password_changed", actor=user)
        return user


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = ["id", "device_id", "platform", "fcm_token", "trusted", "last_seen_at"]
        read_only_fields = ["id", "trusted", "last_seen_at"]

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        device, _ = UserDevice.objects.update_or_create(
            user=request.user,
            company=request.company,
            device_id=validated_data["device_id"],
            defaults={
                "platform": validated_data["platform"],
                "fcm_token": validated_data.get("fcm_token", ""),
                "last_seen_at": timezone.now(),
                "revoked_at": None,
            },
        )
        return device
