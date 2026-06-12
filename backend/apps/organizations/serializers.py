from rest_framework import serializers

from .models import Company, CompanyPolicy, FeatureFlag, WPSConfiguration


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "slug",
            "legal_name",
            "trade_license_number",
            "mohre_establishment_number",
            "emirate",
            "industry",
            "timezone",
            "currency",
            "payroll_frequency",
            "payroll_cutoff_day",
        ]
        read_only_fields = ["id", "slug"]
        extra_kwargs = {
            "trade_license_number": {"write_only": True},
            "mohre_establishment_number": {"write_only": True},
        }


class CompanyPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyPolicy
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PayrollPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyPolicy
        fields = [
            "id",
            "half_day_deduction_percentage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WPSConfigurationSerializer(serializers.ModelSerializer):
    configured = serializers.SerializerMethodField()

    class Meta:
        model = WPSConfiguration
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at", "configured"]
        extra_kwargs = {
            "employer_bank_routing_code": {"write_only": True},
            "employer_account": {"write_only": True},
            "employer_reference": {"write_only": True},
        }

    def get_configured(self, obj):
        return bool(obj.partner_name and obj.is_active)


class FeatureFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureFlag
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at"]
