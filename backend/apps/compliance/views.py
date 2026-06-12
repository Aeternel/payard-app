from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasActiveCompany, RoleAtLeast
from apps.core.services import record_audit

from .models import ComplianceAlert
from .serializers import ComplianceAlertSerializer, ResolveComplianceAlertSerializer
from .tasks import scan_compliance_alerts


class ComplianceAlertViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = ComplianceAlertSerializer
    permission_classes = [HasActiveCompany, RoleAtLeast]
    filterset_fields = ["status", "severity", "alert_type", "occurrence_date"]
    ordering_fields = ["severity", "occurrence_date", "created_at"]

    def get_queryset(self):
        queryset = ComplianceAlert.objects.filter(company=self.request.company)
        if self.request.membership.role == "supervisor":
            queryset = queryset.filter(entity_type__in=["attendance.attendancerecord"])
        return queryset

    @action(detail=False, methods=["post"])
    def scan(self, request):
        scan_compliance_alerts.delay(str(request.company.id))
        return Response({"detail": "Compliance scan queued."}, status=202)

    @action(detail=True, methods=["post"], serializer_class=ResolveComplianceAlertSerializer)
    def resolve(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = self.get_object()
        alert.status = serializer.validated_data["status"]
        alert.resolution = serializer.validated_data["resolution"]
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        record_audit(instance=alert, action="compliance_alert_resolved", actor=request.user)
        return Response(ComplianceAlertSerializer(alert).data)
