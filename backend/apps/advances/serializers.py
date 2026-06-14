from decimal import Decimal

from rest_framework import serializers

from .models import AdvancePolicy, AdvanceRequest
from .services import create_advance_request


class AdvancePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvancePolicy
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        minimum = attrs.get(
            "minimum_amount",
            getattr(self.instance, "minimum_amount", Decimal("0")),
        )
        maximum = attrs.get(
            "maximum_amount",
            getattr(self.instance, "maximum_amount", None),
        )
        roles = attrs.get(
            "approver_roles",
            getattr(self.instance, "approver_roles", []),
        )
        if maximum is not None and maximum < minimum:
            raise serializers.ValidationError(
                {"maximum_amount": "Maximum amount cannot be below the minimum amount."}
            )
        if not roles:
            raise serializers.ValidationError(
                {"approver_roles": "Select at least one approval role."}
            )
        return attrs


class AdvanceRequestSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    worker_code = serializers.CharField(source="worker.worker_code", read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.name", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.name", read_only=True)
    deduction_cycle_name = serializers.CharField(source="deduction_cycle.name", read_only=True)
    available_limit = serializers.SerializerMethodField()

    class Meta:
        model = AdvanceRequest
        exclude = ["company"]
        read_only_fields = [
            "id",
            "available_limit_snapshot",
            "approved_amount",
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "decision_reason",
            "disbursed_at",
            "disbursement_reference",
            "deduction_cycle",
            "acknowledgement_text",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        request = self.context["request"]
        worker = validated_data["worker"]
        if worker.company_id != request.company.id:
            raise serializers.ValidationError("Cross-company reference denied.")
        return create_advance_request(
            worker=worker,
            amount=validated_data["requested_amount"],
            acknowledgement=validated_data["acknowledgement"],
            actor=request.user,
            channel="admin",
        )

    def get_available_limit(self, obj) -> Decimal:
        from .services import available_advance_limit

        return available_advance_limit(obj.worker)


class AdvanceDecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
    )
    reason = serializers.CharField(required=False, allow_blank=True)


class DisbursementSerializer(serializers.Serializer):
    reference = serializers.CharField(min_length=3, max_length=255)
    deduction_cycle = serializers.UUIDField()
