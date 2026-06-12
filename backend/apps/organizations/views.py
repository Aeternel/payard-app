from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasActiveCompany, IsCompanyAdmin, IsPayrollManager
from apps.core.services import model_snapshot, record_audit
from apps.core.viewsets import TenantModelViewSet

from .models import CompanyPolicy, FeatureFlag, WPSConfiguration
from .serializers import (
    CompanyPolicySerializer,
    CompanySerializer,
    FeatureFlagSerializer,
    PayrollPolicySerializer,
    WPSConfigurationSerializer,
)
from .services import setup_readiness


class CompanyViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = CompanySerializer
    permission_classes = [HasActiveCompany, IsCompanyAdmin]

    def get_queryset(self):
        return type(self.request.company).objects.filter(pk=self.request.company.pk)

    @action(detail=True, methods=["get"])
    def readiness(self, request, pk=None):
        return Response(setup_readiness(self.get_object()))

    def perform_update(self, serializer):
        before = model_snapshot(self.get_object())
        company = serializer.save()
        record_audit(instance=company, action="updated", actor=self.request.user, before=before)


class SingletonTenantViewSet(TenantModelViewSet):
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_object(self):
        obj, _ = self.get_queryset().get_or_create(company=self.request.company)
        return obj

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)


class CompanyPolicyViewSet(SingletonTenantViewSet):
    queryset = CompanyPolicy.objects.all()
    serializer_class = CompanyPolicySerializer
    permission_classes = [HasActiveCompany, IsCompanyAdmin]


class PayrollPolicyViewSet(SingletonTenantViewSet):
    queryset = CompanyPolicy.objects.all()
    serializer_class = PayrollPolicySerializer
    permission_classes = [HasActiveCompany, IsPayrollManager]


class WPSConfigurationViewSet(SingletonTenantViewSet):
    queryset = WPSConfiguration.objects.all()
    serializer_class = WPSConfigurationSerializer
    permission_classes = [HasActiveCompany, IsCompanyAdmin]


class FeatureFlagViewSet(TenantModelViewSet):
    queryset = FeatureFlag.objects.all()
    serializer_class = FeatureFlagSerializer
    permission_classes = [HasActiveCompany, IsCompanyAdmin]
    filterset_fields = ["key", "enabled"]
