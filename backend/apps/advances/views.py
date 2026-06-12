from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasActiveCompany, IsFinanceApprover
from apps.core.viewsets import TenantModelViewSet
from apps.payroll.models import PayrollCycle

from .models import AdvancePolicy, AdvanceRequest
from .serializers import (
    AdvanceDecisionSerializer,
    AdvancePolicySerializer,
    AdvanceRequestSerializer,
    DisbursementSerializer,
)
from .services import decide_advance, mark_disbursed


class AdvancePolicyViewSet(TenantModelViewSet):
    queryset = AdvancePolicy.objects.all()
    serializer_class = AdvancePolicySerializer
    permission_classes = [HasActiveCompany, IsFinanceApprover]
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_object(self):
        obj, _ = AdvancePolicy.objects.get_or_create(company=self.request.company)
        return obj

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)


class AdvanceRequestViewSet(TenantModelViewSet):
    queryset = AdvanceRequest.objects.select_related("worker", "approved_by", "deduction_cycle")
    serializer_class = AdvanceRequestSerializer
    filterset_fields = ["worker", "status", "deduction_cycle"]
    ordering_fields = ["requested_amount", "created_at"]

    def scope_supervisor_queryset(self, queryset):
        return queryset.filter(worker__supervisor=self.request.user)

    @action(
        detail=True,
        methods=["post"],
        serializer_class=AdvanceDecisionSerializer,
        permission_classes=[HasActiveCompany, IsFinanceApprover],
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
        permission_classes=[HasActiveCompany, IsFinanceApprover],
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
