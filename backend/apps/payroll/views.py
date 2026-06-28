from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import (
    CanBuildPayroll,
    CanViewPayroll,
    HasActiveCompany,
    IsFinanceApprover,
    IsPayrollManager,
    IsPayrollOperator,
)
from apps.core.scoping import apply_active_supervisor_site_scope
from apps.core.services import model_snapshot, record_audit
from apps.core.viewsets import TenantModelViewSet

from .models import (
    DailyWageLedger,
    PayrollAdjustment,
    PayrollCycle,
    PayrollExport,
    PayrollLine,
    WageRule,
)
from .reports import (
    build_excel_report,
    build_html_report,
    build_pdf_report,
    report_data,
)
from .serializers import (
    DailyWageLedgerSerializer,
    PayrollAdjustmentSerializer,
    PayrollCycleSerializer,
    PayrollExportSerializer,
    PayrollLineOverrideSerializer,
    PayrollLineSerializer,
    WageRuleSerializer,
)
from .services import (
    build_payroll_lines,
    lock_payroll,
    payroll_line_daily_breakdown,
    payroll_readiness,
)
from .tasks import generate_wps_export


class WageRuleViewSet(TenantModelViewSet):
    queryset = WageRule.objects.all()
    serializer_class = WageRuleSerializer
    permission_classes = [HasActiveCompany, IsPayrollOperator]
    filterset_fields = ["is_active", "worker", "site"]

    def perform_update(self, serializer):
        instance = serializer.save(version=serializer.instance.version + 1)
        record_audit(instance=instance, action="wage_rule_versioned", actor=self.request.user)


class DailyWageLedgerViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = DailyWageLedgerSerializer
    permission_classes = [HasActiveCompany]
    filterset_fields = ["worker", "work_date", "status"]
    ordering_fields = ["work_date", "net_estimate"]

    def get_queryset(self):
        queryset = DailyWageLedger.objects.filter(company=self.request.company).select_related(
            "worker", "attendance"
        )
        return apply_active_supervisor_site_scope(
            queryset, request=self.request, site_lookup="attendance__site_id"
        )


class PayrollCycleViewSet(TenantModelViewSet):
    queryset = PayrollCycle.objects.all()
    serializer_class = PayrollCycleSerializer
    permission_classes = [HasActiveCompany, CanViewPayroll]
    filterset_fields = ["status", "period_start", "period_end"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(line_count=Count("lines"))
            .annotate(total_net_pay=Sum("lines__net_pay"))
            .select_related("submitted_by", "approved_by", "locked_by")
        )

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [HasActiveCompany(), IsPayrollManager()]
        if self.action == "build":
            return [HasActiveCompany(), CanBuildPayroll()]
        return super().get_permissions()

    def perform_update(self, serializer):
        cycle = self.get_object()
        if cycle.status != PayrollCycle.Status.DRAFT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Only draft payroll cycles can be edited.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status != PayrollCycle.Status.DRAFT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Only draft payroll cycles can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["get"])
    def readiness(self, request, pk=None):
        return Response(payroll_readiness(self.get_object()))

    @action(detail=True, methods=["post"])
    def build(self, request, pk=None):
        cycle = build_payroll_lines(self.get_object(), request.user)
        return Response(self.get_serializer(cycle).data)

    def _report(self, request, report_format):
        cycle = self.get_object()
        if not cycle.lines.exists():
            return Response(
                {"detail": "Build the payroll cycle before generating reports."},
                status=status.HTTP_409_CONFLICT,
            )
        report = report_data(cycle)
        if report_format == "html":
            content = build_html_report(report).encode()
            filename = f"payyard-{cycle.period_start}-{cycle.period_end}.html"
            content_type = "text/html; charset=utf-8"
            disposition = "inline"
        elif report_format == "pdf":
            content, filename = build_pdf_report(report)
            content_type = "application/pdf"
            disposition = "attachment"
        else:
            content, filename = build_excel_report(report)
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            disposition = "attachment"
        record_audit(
            instance=cycle,
            action="payroll_report_downloaded",
            actor=request.user,
            metadata={
                "format": report_format,
                "worker_count": report.totals["worker_count"],
                "cycle_status": cycle.status,
            },
        )
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=True, methods=["get"], url_path="report-html")
    def report_html(self, request, pk=None):
        return self._report(request, "html")

    @action(detail=True, methods=["get"], url_path="report-pdf")
    def report_pdf(self, request, pk=None):
        return self._report(request, "pdf")

    @action(detail=True, methods=["get"], url_path="report-excel")
    def report_excel(self, request, pk=None):
        return self._report(request, "excel")

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[HasActiveCompany, IsFinanceApprover],
    )
    @transaction.atomic
    def approve(self, request, pk=None):
        cycle = PayrollCycle.objects.select_for_update().get(pk=self.get_object().pk)
        if cycle.status != PayrollCycle.Status.REVIEW:
            return Response({"detail": "Cycle must be in review."}, status=409)
        if cycle.lines.filter(
            flags__contains=["below_contract_baseline"]
        ).exists() and not request.data.get("below_contract_reason"):
            return Response(
                {"detail": "Below-contract lines require an approval reason."}, status=409
            )
        cycle.status = PayrollCycle.Status.APPROVED
        cycle.approved_by = request.user
        cycle.approved_at = timezone.now()
        cycle.save()
        record_audit(
            instance=cycle,
            action="payroll_approved",
            actor=request.user,
            metadata={"reason": request.data.get("below_contract_reason", "")},
        )
        return Response(self.get_serializer(cycle).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[HasActiveCompany, IsFinanceApprover],
    )
    def lock(self, request, pk=None):
        cycle = lock_payroll(self.get_object(), request.user)
        return Response(self.get_serializer(cycle).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[HasActiveCompany, IsFinanceApprover],
    )
    @transaction.atomic
    def export(self, request, pk=None):
        cycle = self.get_object()
        if cycle.status not in {PayrollCycle.Status.LOCKED, PayrollCycle.Status.EXPORTED}:
            return Response({"detail": "Payroll must be locked before export."}, status=409)
        version = cycle.exports.filter(export_type="wps").count() + 1
        export = PayrollExport.objects.create(
            company=request.company,
            cycle=cycle,
            export_type="wps",
            version=version,
            requested_by=request.user,
        )
        transaction.on_commit(lambda: generate_wps_export.delay(str(export.id)))
        record_audit(instance=export, action="wps_export_requested", actor=request.user)
        return Response(
            PayrollExportSerializer(export, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class PayrollLineViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PayrollLineSerializer
    permission_classes = [HasActiveCompany, CanViewPayroll]
    filterset_fields = ["cycle", "worker"]
    ordering_fields = ["net_pay", "gross_pay"]

    def get_queryset(self):
        return PayrollLine.objects.filter(company=self.request.company).select_related(
            "company__policy", "cycle", "worker", "manual_override_by"
        )

    @action(detail=True, methods=["get"], url_path="daily-breakdown")
    def daily_breakdown(self, request, pk=None):
        return Response(payroll_line_daily_breakdown(self.get_object()))

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[HasActiveCompany, IsPayrollManager],
    )
    @transaction.atomic
    def override(self, request, pk=None):
        line = (
            PayrollLine.objects.select_for_update()
            .select_related("cycle")
            .get(pk=self.get_object().pk)
        )
        if line.cycle.status not in {
            PayrollCycle.Status.DRAFT,
            PayrollCycle.Status.REVIEW,
        }:
            return Response(
                {"detail": "Pay can only be changed before cycle approval."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = PayrollLineOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = model_snapshot(line)
        amount = serializer.validated_data["net_pay"]
        reason = serializer.validated_data["reason"]
        line.manual_net_pay = amount
        line.manual_override_reason = reason
        line.manual_override_by = request.user
        line.manual_override_at = timezone.now()
        line.net_pay = amount if amount is not None else line.calculated_net_pay
        line.flags = [
            flag for flag in line.flags if flag != "manual_net_override"
        ]
        if amount is not None:
            line.flags.append("manual_net_override")
        line.save(
            update_fields=[
                "manual_net_pay",
                "manual_override_reason",
                "manual_override_by",
                "manual_override_at",
                "net_pay",
                "flags",
                "updated_at",
            ]
        )
        record_audit(
            instance=line,
            action=(
                "payroll_line_overridden"
                if amount is not None
                else "payroll_line_override_cleared"
            ),
            actor=request.user,
            before=before,
            metadata={"reason": reason},
        )
        return Response(self.get_serializer(line).data)


class PayrollAdjustmentViewSet(TenantModelViewSet):
    queryset = PayrollAdjustment.objects.select_related("cycle", "worker")
    serializer_class = PayrollAdjustmentSerializer
    permission_classes = [HasActiveCompany, IsPayrollOperator]
    filterset_fields = ["cycle", "worker", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(company=self.request.company, requested_by=self.request.user)
        record_audit(
            instance=instance, action="payroll_adjustment_requested", actor=self.request.user
        )


class PayrollExportViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PayrollExportSerializer
    permission_classes = [HasActiveCompany, IsFinanceApprover]
    filterset_fields = ["cycle", "status", "export_type"]

    def get_queryset(self):
        return PayrollExport.objects.filter(company=self.request.company).select_related("cycle")
