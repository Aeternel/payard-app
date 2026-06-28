from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.permissions import (
    CanCreateDisputes,
    HasActiveCompany,
    IsDisputeResolver,
)
from apps.core.scoping import apply_active_supervisor_worker_scope, supervisor_has_worker_access
from apps.core.services import record_audit
from apps.core.viewsets import TenantModelViewSet
from apps.payroll.models import PayrollAdjustment

from .models import Dispute, DisputeComment, DisputeEvidence
from .serializers import (
    DisputeCommentSerializer,
    DisputeEvidenceSerializer,
    DisputeSerializer,
    RejectDisputeSerializer,
    ResolveDisputeSerializer,
)


class DisputeViewSet(TenantModelViewSet):
    queryset = Dispute.objects.select_related(
        "worker",
        "assigned_to",
        "resolved_by",
        "linked_attendance",
        "linked_payroll_line__cycle",
        "linked_adjustment",
    ).prefetch_related("evidence", "comments__author")
    serializer_class = DisputeSerializer
    filterset_fields = ["worker", "status", "priority", "dispute_type", "assigned_to"]
    search_fields = ["worker__worker_code", "worker__full_name", "description"]
    http_method_names = ["get", "post", "head", "options"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup="worker"
        )

    def get_permissions(self):
        if self.action == "create":
            return [HasActiveCompany(), CanCreateDisputes()]
        return super().get_permissions()

    def perform_create(self, serializer):
        worker = serializer.validated_data["worker"]
        if not supervisor_has_worker_access(self.request, worker):
            raise PermissionDenied("Supervisors can only open disputes for their workers.")
        assigned_to = worker.supervisor
        initial_status = (
            Dispute.Status.SUPERVISOR_REVIEW
            if assigned_to
            else Dispute.Status.HR_REVIEW
        )
        instance = serializer.save(
            company=self.request.company,
            assigned_to=assigned_to,
            status=initial_status,
            sla_due_at=timezone.now() + timedelta(hours=48),
        )
        record_audit(instance=instance, action="dispute_opened", actor=self.request.user)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[HasActiveCompany, CanCreateDisputes],
    )
    def escalate(self, request, pk=None):
        dispute = self.get_object()
        if dispute.status not in {
            Dispute.Status.OPEN,
            Dispute.Status.SUPERVISOR_REVIEW,
        }:
            return Response(
                {"detail": "Only an open supervisor case can be escalated."},
                status=409,
            )
        dispute.status = Dispute.Status.HR_REVIEW
        dispute.escalated_at = timezone.now()
        dispute.assigned_to = None
        dispute.save()
        record_audit(instance=dispute, action="dispute_escalated", actor=request.user)
        return Response(self.get_serializer(dispute).data)

    @action(
        detail=True,
        methods=["post"],
        serializer_class=ResolveDisputeSerializer,
        permission_classes=[HasActiveCompany, IsDisputeResolver],
    )
    @transaction.atomic
    def resolve(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispute = Dispute.objects.select_for_update().get(pk=self.get_object().pk)
        if dispute.status in {Dispute.Status.RESOLVED, Dispute.Status.REJECTED}:
            return Response({"detail": "This dispute is already closed."}, status=409)
        adjustment_amount = serializer.validated_data.get("adjustment_amount")
        if adjustment_amount is not None:
            if not dispute.linked_payroll_line_id:
                return Response(
                    {"detail": "A payroll line is required for adjustment."}, status=409
                )
            adjustment = PayrollAdjustment.objects.create(
                company=request.company,
                cycle=dispute.linked_payroll_line.cycle,
                worker=dispute.worker,
                source_type="dispute",
                source_id=dispute.id,
                amount=adjustment_amount,
                reason=serializer.validated_data["resolution"],
                requested_by=request.user,
            )
            dispute.linked_adjustment = adjustment
        dispute.status = Dispute.Status.RESOLVED
        dispute.resolution = serializer.validated_data["resolution"]
        dispute.resolved_at = timezone.now()
        dispute.resolved_by = request.user
        dispute.save()
        record_audit(instance=dispute, action="dispute_resolved", actor=request.user)
        return Response(DisputeSerializer(dispute).data)

    @action(
        detail=True,
        methods=["post"],
        serializer_class=RejectDisputeSerializer,
        permission_classes=[HasActiveCompany, IsDisputeResolver],
    )
    @transaction.atomic
    def reject(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispute = Dispute.objects.select_for_update().get(pk=self.get_object().pk)
        if dispute.status in {Dispute.Status.RESOLVED, Dispute.Status.REJECTED}:
            return Response({"detail": "This dispute is already closed."}, status=409)
        dispute.status = Dispute.Status.REJECTED
        dispute.resolution = serializer.validated_data["reason"]
        dispute.resolved_at = timezone.now()
        dispute.resolved_by = request.user
        dispute.save()
        record_audit(instance=dispute, action="dispute_rejected", actor=request.user)
        return Response(DisputeSerializer(dispute).data)


class DisputeEvidenceViewSet(TenantModelViewSet):
    queryset = DisputeEvidence.objects.select_related("dispute")
    serializer_class = DisputeEvidenceSerializer
    filterset_fields = ["dispute", "evidence_type"]
    http_method_names = ["get", "post", "head", "options"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup="dispute__worker"
        )

    def perform_create(self, serializer):
        dispute = serializer.validated_data["dispute"]
        if dispute.company_id != self.request.company.id:
            raise PermissionDenied("Cross-company reference denied.")
        if not supervisor_has_worker_access(self.request, dispute.worker):
            raise PermissionDenied("Supervisors can only add evidence to their workers' cases.")
        instance = serializer.save(company=self.request.company, uploaded_by=self.request.user)
        record_audit(instance=instance, action="dispute_evidence_added", actor=self.request.user)


class DisputeCommentViewSet(TenantModelViewSet):
    queryset = DisputeComment.objects.select_related("dispute", "author")
    serializer_class = DisputeCommentSerializer
    filterset_fields = ["dispute", "is_worker_visible"]
    http_method_names = ["get", "post", "head", "options"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup="dispute__worker"
        )

    def perform_create(self, serializer):
        dispute = serializer.validated_data["dispute"]
        if dispute.company_id != self.request.company.id:
            raise PermissionDenied("Cross-company reference denied.")
        if not supervisor_has_worker_access(self.request, dispute.worker):
            raise PermissionDenied("Supervisors can only comment on their workers' cases.")
        instance = serializer.save(company=self.request.company, author=self.request.user)
        record_audit(instance=instance, action="dispute_commented", actor=self.request.user)
