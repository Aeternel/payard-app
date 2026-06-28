from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Membership
from apps.core.permissions import HasActiveCompany, IsWorkforceManager, RoleAtLeast
from apps.core.scoping import apply_active_supervisor_worker_scope
from apps.core.services import record_audit
from apps.core.viewsets import TenantModelViewSet

from .models import ConsentRecord, Worker, WorkerDocument
from .serializers import ConsentRecordSerializer, WorkerDocumentSerializer, WorkerSerializer


class WorkerViewSet(TenantModelViewSet):
    queryset = Worker.objects.select_related("default_site", "supervisor")
    serializer_class = WorkerSerializer
    filterset_fields = ["status", "wage_type", "default_site", "supervisor"]
    search_fields = ["worker_code", "full_name", "phone"]
    ordering_fields = ["worker_code", "full_name", "employment_start_date", "created_at"]

    def get_permissions(self):
        if self.action in {
            "create",
            "update",
            "partial_update",
            "destroy",
            "activate",
            "creation_options",
        }:
            return [HasActiveCompany(), IsWorkforceManager()]
        return super().get_permissions()

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup=""
        )

    @action(detail=False, methods=["get"], url_path="creation-options")
    def creation_options(self, request):
        sites = request.company.site_set.filter(is_active=True).order_by("name")
        active_site_links = request.company.sitesupervisor_set.filter(
            active_from__lte=timezone.localdate(),
        ).filter(
            Q(active_until__isnull=True) | Q(active_until__gte=timezone.localdate())
        )
        supervisors = (
            Membership.objects.filter(
                company=request.company,
                role=Membership.Role.SUPERVISOR,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .prefetch_related(
                Prefetch(
                    "user__site_links",
                    queryset=active_site_links,
                    to_attr="active_site_links",
                )
            )
            .order_by("user__name")
        )
        return Response(
            {
                "sites": [
                    {"id": str(site.id), "name": site.name, "address": site.address}
                    for site in sites
                ],
                "supervisors": [
                    {
                        "id": str(membership.user_id),
                        "name": membership.user.name,
                        "phone": membership.user.phone,
                        "site_ids": [
                            str(link.site_id)
                            for link in membership.user.active_site_links
                        ],
                    }
                    for membership in supervisors
                ],
                "wage_types": [
                    {"value": value, "label": label}
                    for value, label in Worker.WageType.choices
                ],
                "notification_channels": [
                    {"value": value, "label": label}
                    for value, label in Worker.NotificationChannel.choices
                ],
            }
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def activate(self, request, pk=None):
        worker = self.get_object()
        missing = []
        if worker.basic_wage <= 0:
            missing.append("basic_wage")
        if not worker.default_site_id:
            missing.append("default_site")
        if not worker.supervisor_id:
            missing.append("supervisor")
        if missing:
            return Response({"detail": "Worker is incomplete.", "missing": missing}, status=409)
        worker.status = Worker.Status.ACTIVE
        worker.save(update_fields=["status", "updated_at"])
        record_audit(instance=worker, action="activated", actor=request.user)
        return Response(self.get_serializer(worker).data)


class WorkerDocumentViewSet(TenantModelViewSet):
    queryset = WorkerDocument.objects.select_related("worker")
    serializer_class = WorkerDocumentSerializer
    filterset_fields = ["worker", "document_type", "status"]
    ordering_fields = ["expiry_date", "created_at"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup="worker"
        )

    @action(detail=True, methods=["post"], permission_classes=[HasActiveCompany, RoleAtLeast])
    def verify(self, request, pk=None):
        document = self.get_object()
        document.verified_at = timezone.now()
        document.verified_by = request.user
        document.status = "verified"
        document.save(update_fields=["verified_at", "verified_by", "status", "updated_at"])
        record_audit(instance=document, action="verified", actor=request.user)
        return Response(self.get_serializer(document).data)


class ConsentRecordViewSet(TenantModelViewSet):
    queryset = ConsentRecord.objects.select_related("worker", "captured_by")
    serializer_class = ConsentRecordSerializer
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["worker", "consent_type", "status"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup="worker"
        )

    def perform_create(self, serializer):
        instance = serializer.save(company=self.request.company, captured_by=self.request.user)
        record_audit(instance=instance, action="consent_recorded", actor=self.request.user)
