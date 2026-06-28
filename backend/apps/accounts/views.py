from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.permissions import HasActiveCompany, IsCompanyAdmin
from apps.core.services import model_snapshot, record_audit
from apps.payroll.models import PayrollCycle
from apps.payroll.serializers import PayrollLineSerializer

from .models import Membership, UserDevice
from .serializers import (
    CompanyTokenSerializer,
    DeviceSerializer,
    MembershipSerializer,
    PasswordChangeSerializer,
    StaffOnboardingSerializer,
    StaffPayrollProfileSerializer,
    UserSerializer,
)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CompanyTokenSerializer


class MeView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, HasActiveCompany]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        data = super().retrieve(request, *args, **kwargs).data
        data["company"] = {
            "id": str(request.company.id),
            "name": request.company.name,
            "slug": request.company.slug,
        }
        data["role"] = request.membership.role
        data["permissions"] = request.membership.permission_overrides
        payroll_profile = getattr(request.user, "payroll_profile", None)
        data["payroll_profile_id"] = (
            str(payroll_profile.id)
            if payroll_profile and payroll_profile.company_id == request.company.id
            else None
        )
        return Response(data)


class MyPayrollView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, HasActiveCompany]

    def get(self, request):
        worker = getattr(request.user, "payroll_profile", None)
        if not worker or worker.company_id != request.company.id:
            return Response({"profile": None, "payslips": []})
        lines = (
            worker.payroll_lines.filter(
                company=request.company,
                cycle__status__in=[
                    PayrollCycle.Status.LOCKED,
                    PayrollCycle.Status.EXPORTED,
                    PayrollCycle.Status.PAID,
                ],
            )
            .select_related("worker", "cycle")
            .order_by("-cycle__period_end")
            [:24]
        )
        return Response(
            {
                "profile": {
                    "id": str(worker.id),
                    "worker_code": worker.worker_code,
                    "full_name": worker.full_name,
                    "job_title": worker.job_title,
                    "department": worker.department,
                    "basic_wage": str(worker.basic_wage),
                    "currency": request.company.currency,
                },
                "payslips": PayrollLineSerializer(lines, many=True).data,
            }
        )


class PasswordChangeView(generics.GenericAPIView):
    serializer_class = PasswordChangeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipSerializer
    permission_classes = [IsAuthenticated, HasActiveCompany, IsCompanyAdmin]
    filterset_fields = ["role", "is_active"]
    search_fields = ["user__name", "user__phone", "user__email"]

    def get_queryset(self):
        return Membership.objects.filter(company=self.request.company).select_related("user")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, invited_by=self.request.user)

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Use the staff onboarding endpoint to create company access."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=["post"], url_path="onboard")
    def onboard(self, request):
        serializer = StaffOnboardingSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return Response(
            self.get_serializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="payroll-profile")
    def payroll_profile(self, request, pk=None):
        membership = self.get_object()
        serializer = StaffPayrollProfileSerializer(
            data=request.data,
            context={"request": request, "membership": membership},
        )
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(
            {
                "id": str(profile.id),
                "worker_code": profile.worker_code,
                "full_name": profile.full_name,
            },
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        membership = self.get_object()
        if (
            self.request.membership.role != Membership.Role.OWNER
            and membership.role in {Membership.Role.OWNER, Membership.Role.ADMIN}
        ):
            raise PermissionDenied("Only an owner can modify owner or admin access.")
        before = model_snapshot(membership)
        instance = serializer.save()
        record_audit(
            instance=instance,
            action="membership_updated",
            actor=self.request.user,
            before=before,
        )

    def perform_destroy(self, instance):
        if (
            self.request.membership.role != Membership.Role.OWNER
            and instance.role in {Membership.Role.OWNER, Membership.Role.ADMIN}
        ):
            raise PermissionDenied("Only an owner can remove owner or admin access.")
        if (
            instance.role == Membership.Role.OWNER
            and instance.is_active
            and Membership.objects.filter(
                company=self.request.company,
                role=Membership.Role.OWNER,
                is_active=True,
            ).count()
            <= 1
        ):
            raise ValidationError("The company must retain at least one active owner.")
        before = model_snapshot(instance)
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        record_audit(
            instance=instance,
            action="membership_deactivated",
            actor=self.request.user,
            before=before,
        )


class DeviceViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated, HasActiveCompany]

    def get_queryset(self):
        return UserDevice.objects.filter(user=self.request.user, company=self.request.company)

    @action(detail=True, methods=["post"])
    def trust(self, request, pk=None):
        if request.membership.role not in {"owner", "admin"}:
            return Response({"detail": "Admin approval required."}, status=403)
        device = self.get_object()
        device.trusted = True
        device.save(update_fields=["trusted", "updated_at"])
        return Response(self.get_serializer(device).data)
