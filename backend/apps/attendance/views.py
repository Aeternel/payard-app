from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasActiveCompany
from apps.core.scoping import apply_active_supervisor_site_scope
from apps.core.services import record_audit
from apps.core.viewsets import TenantModelViewSet

from .models import AttendanceException, AttendanceRecord, OvertimeRequest
from .serializers import (
    AttendanceDecisionSerializer,
    AttendanceExceptionSerializer,
    AttendanceRecordSerializer,
    CheckInSerializer,
    CheckOutSerializer,
    DecisionSerializer,
    OfflineSyncSerializer,
    OvertimeRequestSerializer,
)
from .services import check_in, check_out, decide_exception


class AttendanceRecordViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = AttendanceRecord.objects.none()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [HasActiveCompany]
    filterset_fields = ["worker", "site", "work_date", "status", "verification_method"]
    search_fields = ["worker__worker_code", "worker__full_name"]
    ordering_fields = ["work_date", "check_in_at", "created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        queryset = AttendanceRecord.objects.filter(company=self.request.company).select_related(
            "worker", "site", "shift", "roster_assignment"
        )
        return apply_active_supervisor_site_scope(
            queryset, request=self.request, site_lookup="site_id"
        )

    @action(detail=False, methods=["post"], serializer_class=CheckInSerializer)
    def check_in(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, created = check_in(
            company=request.company,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(
            AttendanceRecordSerializer(record).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], serializer_class=CheckOutSerializer)
    def check_out(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = check_out(
            record=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(AttendanceRecordSerializer(record).data)

    @action(detail=False, methods=["post"], serializer_class=OfflineSyncSerializer)
    def sync(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = []
        for item in serializer.validated_data["records"]:
            try:
                record, created = check_in(
                    company=request.company,
                    actor=request.user,
                    source=AttendanceRecord.Source.OFFLINE_SYNC,
                    **item,
                )
                results.append(
                    {
                        "idempotency_key": item["idempotency_key"],
                        "id": record.id,
                        "created": created,
                    }
                )
            except Exception as exc:
                results.append({"idempotency_key": item["idempotency_key"], "error": str(exc)})
        return Response({"results": results}, status=status.HTTP_207_MULTI_STATUS)


class AttendanceExceptionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = AttendanceException.objects.none()
    serializer_class = AttendanceExceptionSerializer
    permission_classes = [HasActiveCompany]
    filterset_fields = ["attendance", "exception_type", "status"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        queryset = AttendanceException.objects.filter(company=self.request.company).select_related(
            "attendance", "attendance__worker", "decided_by"
        )
        return apply_active_supervisor_site_scope(
            queryset, request=self.request, site_lookup="attendance__site_id"
        )

    @action(
        detail=True,
        methods=["post"],
        serializer_class=AttendanceDecisionSerializer,
    )
    def decide(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exception = decide_exception(
            exception=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(AttendanceExceptionSerializer(exception).data)


class OvertimeRequestViewSet(TenantModelViewSet):
    queryset = OvertimeRequest.objects.select_related("attendance", "requested_by", "decided_by")
    serializer_class = OvertimeRequestSerializer
    filterset_fields = ["attendance", "status", "requested_by"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_site_scope(
            queryset, request=self.request, site_lookup="attendance__site_id"
        )

    def perform_create(self, serializer):
        instance = serializer.save(company=self.request.company, requested_by=self.request.user)
        record_audit(instance=instance, action="overtime_requested", actor=self.request.user)

    @action(detail=True, methods=["post"], serializer_class=DecisionSerializer)
    @transaction.atomic
    def decide(self, request, pk=None):
        if request.membership.role == "supervisor":
            return Response({"detail": "Operations approval required."}, status=403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        overtime = OvertimeRequest.objects.select_for_update().get(pk=self.get_object().pk)
        if overtime.status != OvertimeRequest.Status.PENDING:
            return Response({"detail": "Overtime request is already decided."}, status=409)
        approve = serializer.validated_data["approve"]
        overtime.status = (
            OvertimeRequest.Status.APPROVED if approve else OvertimeRequest.Status.REJECTED
        )
        overtime.approved_minutes = overtime.requested_minutes if approve else 0
        overtime.decided_by = request.user
        overtime.decided_at = timezone.now()
        overtime.decision_reason = serializer.validated_data["reason"]
        overtime.save()
        record_audit(instance=overtime, action="overtime_decided", actor=request.user)
        if approve:
            from apps.payroll.tasks import calculate_daily_wage

            transaction.on_commit(lambda: calculate_daily_wage.delay(str(overtime.attendance_id)))
        return Response(OvertimeRequestSerializer(overtime).data)
