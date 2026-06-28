from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.advances.serializers import AdvanceRequestSerializer
from apps.advances.services import available_advance_limit, create_advance_request
from apps.attendance.serializers import AttendanceRecordSerializer
from apps.disputes.models import Dispute, DisputeComment
from apps.disputes.serializers import DisputeSerializer
from apps.notifications.authentication import WorkerPortalAuthentication
from apps.payroll.serializers import DailyWageLedgerSerializer, PayrollLineSerializer

from .serializers import WorkerSerializer


class IsWorkerSession(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request, "worker", None))


class WorkerPortalBaseView(APIView):
    authentication_classes = [WorkerPortalAuthentication]
    permission_classes = [IsWorkerSession]


class WorkerPortalMeView(WorkerPortalBaseView):
    def get(self, request):
        data = WorkerSerializer(request.worker, context={"request": request}).data
        data["available_advance_limit"] = available_advance_limit(request.worker)
        return Response(data)


class WorkerPortalAttendanceView(WorkerPortalBaseView):
    def get(self, request):
        records = request.worker.attendance_records.select_related(
            "site", "shift", "worker"
        ).order_by("-work_date")[:90]
        return Response(AttendanceRecordSerializer(records, many=True).data)


class WorkerPortalWagesView(WorkerPortalBaseView):
    def get(self, request):
        ledgers = request.worker.wage_ledgers.select_related("worker").order_by("-work_date")[:90]
        return Response(DailyWageLedgerSerializer(ledgers, many=True).data)


class WorkerPortalPayslipsView(WorkerPortalBaseView):
    def get(self, request):
        lines = request.worker.payroll_lines.filter(
            cycle__status__in=["locked", "exported", "paid"]
        ).select_related("worker", "cycle").order_by("-cycle__period_end")[:24]
        return Response(PayrollLineSerializer(lines, many=True).data)


class WorkerPortalAdvancesView(WorkerPortalBaseView):
    def get(self, request):
        advances = request.worker.advance_requests.select_related(
            "requested_by", "approved_by", "deduction_cycle"
        ).order_by("-created_at")[:50]
        return Response(AdvanceRequestSerializer(advances, many=True).data)

    def post(self, request):
        amount = request.data.get("amount")
        acknowledgement = request.data.get("acknowledgement", False)
        if amount is None:
            return Response({"detail": "Amount is required."}, status=400)
        try:
            parsed_amount = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            return Response({"detail": "Enter a valid amount."}, status=400)
        advance = create_advance_request(
            worker=request.worker,
            amount=parsed_amount,
            acknowledgement=acknowledgement,
            channel="portal",
        )
        return Response(AdvanceRequestSerializer(advance).data, status=status.HTTP_201_CREATED)


class WorkerPortalDisputesView(WorkerPortalBaseView):
    def get(self, request):
        disputes = (
            request.worker.disputes.select_related(
                "assigned_to",
                "resolved_by",
                "linked_attendance",
                "linked_payroll_line__cycle",
                "linked_adjustment",
            )
            .prefetch_related(
                "evidence",
                Prefetch(
                    "comments",
                    queryset=DisputeComment.objects.filter(is_worker_visible=True).select_related(
                        "author"
                    ),
                ),
            )
            .order_by("-created_at")[:50]
        )
        return Response(DisputeSerializer(disputes, many=True).data)

    def post(self, request):
        serializer = DisputeSerializer(
            data={**request.data, "worker": str(request.worker.id)},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        dispute = serializer.save(
            company=request.company,
            worker=request.worker,
            assigned_to=request.worker.supervisor,
            status=Dispute.Status.SUPERVISOR_REVIEW,
            raised_via="portal",
            sla_due_at=timezone.now() + timedelta(hours=48),
        )
        return Response(DisputeSerializer(dispute).data, status=status.HTTP_201_CREATED)
