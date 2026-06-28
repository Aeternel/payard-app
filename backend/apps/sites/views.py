from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasActiveCompany, RoleAtLeast
from apps.core.scoping import apply_active_supervisor_site_scope
from apps.core.services import record_audit
from apps.core.viewsets import TenantModelViewSet

from .models import RosterAssignment, ShiftTemplate, Site, SiteSupervisor, WorkerTransfer
from .serializers import (
    RosterAssignmentSerializer,
    ShiftTemplateSerializer,
    SiteSerializer,
    SiteSupervisorSerializer,
    WorkerTransferSerializer,
)


class SiteViewSet(TenantModelViewSet):
    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    filterset_fields = ["environment", "is_active"]
    search_fields = ["name", "client_name", "address"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_site_scope(queryset, request=self.request, site_lookup="id")


class SiteSupervisorViewSet(TenantModelViewSet):
    queryset = SiteSupervisor.objects.select_related("site", "supervisor")
    serializer_class = SiteSupervisorSerializer
    filterset_fields = ["site", "supervisor", "is_primary"]

    def scope_supervisor_queryset(self, queryset):
        queryset = queryset.filter(supervisor=self.request.user)
        return apply_active_supervisor_site_scope(
            queryset, request=self.request, site_lookup="site_id"
        )


class ShiftTemplateViewSet(TenantModelViewSet):
    queryset = ShiftTemplate.objects.all()
    serializer_class = ShiftTemplateSerializer
    filterset_fields = ["is_active", "is_night_shift"]
    search_fields = ["name"]


class RosterAssignmentViewSet(TenantModelViewSet):
    queryset = RosterAssignment.objects.select_related("worker", "site", "shift")
    serializer_class = RosterAssignmentSerializer
    filterset_fields = ["site", "worker", "shift", "date", "status"]
    search_fields = ["worker__worker_code", "worker__full_name"]
    ordering_fields = ["date", "created_at"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_site_scope(
            queryset, request=self.request, site_lookup="site_id"
        )

    def perform_create(self, serializer):
        instance = serializer.save(company=self.request.company, approved_by=self.request.user)
        record_audit(instance=instance, action="rostered", actor=self.request.user)


class WorkerTransferViewSet(TenantModelViewSet):
    queryset = WorkerTransfer.objects.select_related(
        "worker", "from_assignment", "to_site", "to_shift"
    )
    serializer_class = WorkerTransferSerializer
    filterset_fields = ["worker", "status", "to_site"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_site_scope(
            queryset,
            request=self.request,
            site_lookup="from_assignment__site_id",
        )

    def perform_create(self, serializer):
        instance = serializer.save(company=self.request.company, requested_by=self.request.user)
        record_audit(instance=instance, action="transfer_requested", actor=self.request.user)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[HasActiveCompany, RoleAtLeast],
    )
    @transaction.atomic
    def approve(self, request, pk=None):
        transfer = self.get_object()
        if request.membership.role == "supervisor":
            return Response({"detail": "Operations approval required."}, status=403)
        if transfer.status != WorkerTransfer.Status.PENDING:
            return Response({"detail": "Transfer is already decided."}, status=409)
        old = transfer.from_assignment
        old.status = RosterAssignment.Status.REPLACED
        old.save(update_fields=["status", "updated_at"])
        RosterAssignment.objects.create(
            company=request.company,
            worker=transfer.worker,
            site=transfer.to_site,
            shift=transfer.to_shift,
            date=old.date,
            replacement_for=old,
            approved_by=request.user,
        )
        transfer.status = WorkerTransfer.Status.APPROVED
        transfer.decided_by = request.user
        transfer.decided_at = timezone.now()
        transfer.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        record_audit(instance=transfer, action="transfer_approved", actor=request.user)
        return Response(self.get_serializer(transfer).data)
