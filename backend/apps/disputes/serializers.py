from rest_framework import serializers

from .models import Dispute, DisputeComment, DisputeEvidence


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisputeEvidence
        exclude = ["company"]
        read_only_fields = ["id", "uploaded_by", "created_at", "updated_at"]


class DisputeCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.name", read_only=True)

    class Meta:
        model = DisputeComment
        exclude = ["company"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]


class DisputeSerializer(serializers.ModelSerializer):
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    comments = DisputeCommentSerializer(many=True, read_only=True)
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    worker_code = serializers.CharField(source="worker.worker_code", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.name", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.name", read_only=True)
    payroll_cycle_name = serializers.CharField(
        source="linked_payroll_line.cycle.name", read_only=True
    )

    class Meta:
        model = Dispute
        exclude = ["company"]
        read_only_fields = [
            "id",
            "status",
            "assigned_to",
            "sla_due_at",
            "escalated_at",
            "resolution",
            "resolved_at",
            "resolved_by",
            "linked_adjustment",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        company = self.context["request"].company
        for field in ("worker", "linked_attendance", "linked_payroll_line"):
            obj = attrs.get(field)
            if obj and obj.company_id != company.id:
                raise serializers.ValidationError({field: "Cross-company reference denied."})
        return attrs


class ResolveDisputeSerializer(serializers.Serializer):
    resolution = serializers.CharField(min_length=3)
    adjustment_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class RejectDisputeSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3)
