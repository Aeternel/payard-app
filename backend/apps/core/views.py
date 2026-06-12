from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog
from .permissions import HasActiveCompany, IsCompanyAdmin
from .serializers import AuditLogSerializer


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"status": "ok", "service": "payyard-api"})


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = AuditLog.objects.none()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, HasActiveCompany, IsCompanyAdmin]
    filterset_fields = ["action", "entity_type", "entity_id", "actor"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return AuditLog.objects.filter(company=self.request.company).select_related("actor")
