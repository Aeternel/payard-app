from rest_framework import serializers

from .models import RosterAssignment, ShiftTemplate, Site, SiteSupervisor, WorkerTransfer


class CompanyReferenceValidationMixin:
    company_fields = ()

    def validate(self, attrs):
        company_id = self.context["request"].company.id
        errors = {}
        for field in self.company_fields:
            value = attrs.get(field)
            if value and value.company_id != company_id:
                errors[field] = "Cross-company reference denied."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SiteSupervisorSerializer(CompanyReferenceValidationMixin, serializers.ModelSerializer):
    company_fields = ("site",)

    class Meta:
        model = SiteSupervisor
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        supervisor = attrs.get("supervisor")
        if (
            supervisor
            and not supervisor.memberships.filter(
                company=self.context["request"].company,
                role="supervisor",
                is_active=True,
            ).exists()
        ):
            raise serializers.ValidationError({"supervisor": "Active supervisor role required."})
        return attrs


class ShiftTemplateSerializer(serializers.ModelSerializer):
    crosses_midnight = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShiftTemplate
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at", "crosses_midnight"]


class RosterAssignmentSerializer(CompanyReferenceValidationMixin, serializers.ModelSerializer):
    company_fields = ("worker", "site", "shift")

    class Meta:
        model = RosterAssignment
        exclude = ["company"]
        read_only_fields = ["id", "approved_by", "created_at", "updated_at"]


class WorkerTransferSerializer(CompanyReferenceValidationMixin, serializers.ModelSerializer):
    company_fields = ("worker", "from_assignment", "to_site", "to_shift")

    class Meta:
        model = WorkerTransfer
        exclude = ["company"]
        read_only_fields = [
            "id",
            "requested_by",
            "decided_by",
            "decided_at",
            "created_at",
            "updated_at",
        ]
