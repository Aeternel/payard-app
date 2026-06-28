from decimal import Decimal

from rest_framework import serializers

from .models import (
    DailyWageLedger,
    PayrollAdjustment,
    PayrollCycle,
    PayrollExport,
    PayrollLine,
    WageRule,
)


class WageRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = WageRule
        exclude = ["company"]
        read_only_fields = ["id", "version", "created_at", "updated_at"]

    def validate(self, attrs):
        company = self.context["request"].company
        for field in ("worker", "site"):
            obj = attrs.get(field)
            if obj and obj.company_id != company.id:
                raise serializers.ValidationError({field: "Cross-company reference denied."})
        return attrs


class DailyWageLedgerSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    worker_code = serializers.CharField(source="worker.worker_code", read_only=True)

    class Meta:
        model = DailyWageLedger
        exclude = ["company"]
        read_only_fields = [
            field.name for field in DailyWageLedger._meta.fields if field.name != "company"
        ]


class PayrollLineSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    worker_code = serializers.CharField(source="worker.worker_code", read_only=True)
    cycle_name = serializers.CharField(source="cycle.name", read_only=True)
    period_start = serializers.DateField(source="cycle.period_start", read_only=True)
    period_end = serializers.DateField(source="cycle.period_end", read_only=True)
    cycle_status = serializers.CharField(source="cycle.status", read_only=True)

    class Meta:
        model = PayrollLine
        exclude = ["company"]
        read_only_fields = [
            field.name for field in PayrollLine._meta.fields if field.name != "company"
        ]


class PayrollLineOverrideSerializer(serializers.Serializer):
    net_pay = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        allow_null=True,
    )
    reason = serializers.CharField(min_length=5, max_length=1000, trim_whitespace=True)


class PayrollCycleSerializer(serializers.ModelSerializer):
    line_count = serializers.IntegerField(read_only=True)
    total_net_pay = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = PayrollCycle
        exclude = ["company"]
        read_only_fields = [
            "id",
            "status",
            "version",
            "readiness_snapshot",
            "submitted_by",
            "approved_by",
            "locked_by",
            "submitted_at",
            "approved_at",
            "locked_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        start = attrs.get("period_start", getattr(self.instance, "period_start", None))
        end = attrs.get("period_end", getattr(self.instance, "period_end", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"period_end": "Period end must be on or after period start."}
            )
        return attrs


class PayrollAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollAdjustment
        exclude = ["company"]
        read_only_fields = [
            "id",
            "requested_by",
            "approved_by",
            "status",
            "applied_cycle",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        company = self.context["request"].company
        errors = {}
        for field in ("cycle", "worker"):
            obj = attrs.get(field)
            if obj and obj.company_id != company.id:
                errors[field] = "Cross-company reference denied."
        cycle = attrs.get("cycle", getattr(self.instance, "cycle", None))
        worker = attrs.get("worker", getattr(self.instance, "worker", None))
        if cycle and worker and cycle.company_id != worker.company_id:
            errors["worker"] = "Worker and payroll cycle must belong to the same company."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class PayrollExportSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PayrollExport
        exclude = ["company"]
        read_only_fields = [
            "id",
            "version",
            "status",
            "file",
            "checksum",
            "row_count",
            "error",
            "requested_by",
            "completed_at",
            "created_at",
            "updated_at",
            "download_url",
        ]

    def get_download_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request and obj.file else None
