import uuid

from django.conf import settings
from django.core.cache import caches
from django.db import connections
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework import status as http_status
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
        return Response(
            {
                "status": "ok",
                "service": "payyard-api",
                "environment": settings.ENVIRONMENT,
                "version": settings.APP_VERSION,
            }
        )


class ReadinessView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(responses={200: dict, 503: dict})
    def get(self, request):
        checks = {
            "database": self._check_database(),
            "cache": self._check_cache(),
        }
        is_ready = all(result["status"] == "ok" for result in checks.values())
        return Response(
            {
                "status": "ok" if is_ready else "degraded",
                "service": "payyard-api",
                "environment": settings.ENVIRONMENT,
                "version": settings.APP_VERSION,
                "checks": checks,
            },
            status=http_status.HTTP_200_OK if is_ready else http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def _check_database(self):
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def _check_cache(self):
        try:
            cache = caches["default"]
            key = f"readiness:{uuid.uuid4()}"
            cache.set(key, "ok", timeout=5)
            if cache.get(key) != "ok":
                raise RuntimeError("Cache round-trip failed.")
            cache.delete(key)
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}


class SchemaView(APIView):
    authentication_classes = []
    permission_classes = []

    def dispatch(self, request, *args, **kwargs):
        if not settings.ENABLE_API_DOCS:
            raise Http404()
        spectacular_view = self.spectacular_view_class.as_view()
        return spectacular_view(request, *args, **kwargs)


class DocsView(APIView):
    authentication_classes = []
    permission_classes = []

    def dispatch(self, request, *args, **kwargs):
        if not settings.ENABLE_API_DOCS:
            raise Http404()
        swagger_view = self.swagger_view_class.as_view(url_name="schema")
        return swagger_view(request, *args, **kwargs)


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
