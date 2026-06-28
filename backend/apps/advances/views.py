from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import (
    HasActiveCompany,
    IsAdvanceDisburser,
    IsFinanceApprover,
    IsWorkforceManager,
)
from apps.core.scoping import apply_active_supervisor_worker_scope
from apps.core.viewsets import TenantModelViewSet
from apps.payroll.models import PayrollCycle
from apps.workforce.models import Worker

from .models import AdvancePolicy, AdvanceRequest
from .serializers import (
    AdvanceDecisionSerializer,
    AdvancePolicySerializer,
    AdvanceRequestSerializer,
    DisbursementSerializer,
)
from .services import (
    available_advance_limit,
    cancel_advance,
    decide_advance,
    mark_disbursed,
)


class AdvancePolicyViewSet(TenantModelViewSet):
    queryset = AdvancePolicy.objects.all()
    serializer_class = AdvancePolicySerializer
    permission_classes = [HasActiveCompany, IsFinanceApprover]
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [HasActiveCompany()]
        return super().get_permissions()

    def get_object(self):
        obj, _ = AdvancePolicy.objects.get_or_create(company=self.request.company)
        return obj

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)


class AdvanceRequestViewSet(TenantModelViewSet):
    queryset = AdvanceRequest.objects.select_related(
        "worker", "requested_by", "approved_by", "deduction_cycle"
    )
    serializer_class = AdvanceRequestSerializer
    filterset_fields = ["worker", "status", "deduction_cycle"]
    ordering_fields = ["requested_amount", "created_at"]
    http_method_names = ["get", "post", "head", "options"]

    def scope_supervisor_queryset(self, queryset):
        return apply_active_supervisor_worker_scope(
            queryset, request=self.request, worker_lookup="worker"
        )

    def get_permissions(self):
        if self.action == "create":
            return [HasActiveCompany(), IsWorkforceManager()]
        return super().get_permissions()

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[HasActiveCompany, IsWorkforceManager],
    )
    def eligibility(self, request):
        worker = Worker.objects.filter(
            company=request.company,
            pk=request.query_params.get("worker"),
        ).first()
        if not worker:
            return Response({"detail": "Worker not found."}, status=404)
        policy = AdvancePolicy.objects.filter(company=request.company, enabled=True).first()
        return Response(
            {
                "worker": str(worker.id),
                "available_limit": available_advance_limit(worker),
                "minimum_amount": policy.minimum_amount if policy else 0,
                "acknowledgement_text": policy.acknowledgement_text if policy else "",
                "enabled": bool(policy),
            }
        )

    @action(
        detail=True,
        methods=["post"],
        serializer_class=AdvanceDecisionSerializer,
        permission_classes=[HasActiveCompany],
    )
    def decide(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        advance = decide_advance(
            advance=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(AdvanceRequestSerializer(advance).data)

    @action(
        detail=True,
        methods=["post"],
        serializer_class=DisbursementSerializer,
        permission_classes=[HasActiveCompany, IsAdvanceDisburser],
    )
    def disburse(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cycle = PayrollCycle.objects.filter(
            company=request.company, pk=serializer.validated_data["deduction_cycle"]
        ).first()
        if not cycle:
            return Response({"detail": "Payroll cycle not found."}, status=404)
        advance = mark_disbursed(
            advance=self.get_object(),
            actor=request.user,
            reference=serializer.validated_data["reference"],
            cycle=cycle,
        )
        return Response(AdvanceRequestSerializer(advance).data)

    @action(detail=True, methods=["post"], permission_classes=[HasActiveCompany])
    def cancel(self, request, pk=None):
        advance = cancel_advance(
            advance=self.get_object(),
            actor=request.user,
        )
        return Response(
            AdvanceRequestSerializer(advance).data,
            status=status.HTTP_200_OK,
        )
