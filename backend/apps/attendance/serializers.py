from rest_framework import serializers

from .models import AttendanceException, AttendanceRecord, OvertimeRequest


class AttendanceRecordSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name", read_only=True)
    worker_code = serializers.CharField(source="worker.worker_code", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    shift_name = serializers.CharField(source="shift.name", read_only=True)

    class Meta:
        model = AttendanceRecord
        exclude = ["company"]
        read_only_fields = [
            field.name for field in AttendanceRecord._meta.fields if field.name != "company"
        ]


class CheckInSerializer(serializers.Serializer):
    roster_assignment = serializers.UUIDField(source="roster_id")
    captured_at = serializers.DateTimeField()
    verification_method = serializers.ChoiceField(
        choices=AttendanceRecord.VerificationMethod.choices
    )
    device_id = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=128)
    notes = serializers.CharField(required=False, allow_blank=True)
    photo = serializers.ImageField(required=False)


class CheckOutSerializer(serializers.Serializer):
    captured_at = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)


class OfflineSyncSerializer(serializers.Serializer):
    records = CheckInSerializer(many=True, max_length=200)


class AttendanceExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceException
        exclude = ["company"]
        read_only_fields = [
            "id",
            "decided_by",
            "decided_at",
            "status",
            "decision",
            "created_at",
            "updated_at",
        ]


class AttendanceDecisionSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=AttendanceException.Decision.choices)
    reason = serializers.CharField(min_length=3, max_length=1000)


class DecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    reason = serializers.CharField(min_length=3, max_length=1000)


class OvertimeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = OvertimeRequest
        exclude = ["company"]
        read_only_fields = [
            "id",
            "requested_by",
            "approved_minutes",
            "status",
            "decided_by",
            "decided_at",
            "decision_reason",
            "created_at",
            "updated_at",
        ]

    def validate_attendance(self, attendance):
        if attendance.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Cross-company reference denied.")
        if not attendance.check_out_at:
            raise serializers.ValidationError("Checkout is required before overtime submission.")
        return attendance
