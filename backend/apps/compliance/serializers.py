from rest_framework import serializers

from .models import ComplianceAlert


class ComplianceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceAlert
        exclude = ["company"]
        read_only_fields = [
            "id",
            "alert_type",
            "severity",
            "title",
            "description",
            "entity_type",
            "entity_id",
            "occurrence_date",
            "unique_key",
            "metadata",
            "resolved_by",
            "resolved_at",
            "created_at",
            "updated_at",
        ]


class ResolveComplianceAlertSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            ComplianceAlert.Status.ACKNOWLEDGED,
            ComplianceAlert.Status.RESOLVED,
            ComplianceAlert.Status.DISMISSED,
        ]
    )
    resolution = serializers.CharField(min_length=3)
