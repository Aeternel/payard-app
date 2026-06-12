import hashlib
import hmac
import json
import uuid

from django.conf import settings
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.permissions import HasActiveCompany, IsCompanyAdmin
from apps.organizations.models import Company

from .models import NotificationOutbox, NotificationTemplate, WhatsAppWebhookEvent
from .serializers import (
    NotificationOutboxSerializer,
    NotificationTemplateSerializer,
    WorkerOTPRequestSerializer,
    WorkerOTPVerifySerializer,
)
from .services import create_worker_otp, verify_worker_otp


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationTemplateSerializer
    permission_classes = [HasActiveCompany, IsCompanyAdmin]

    def get_queryset(self):
        return NotificationTemplate.objects.filter(company=self.request.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class NotificationOutboxViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = NotificationOutboxSerializer
    permission_classes = [HasActiveCompany, IsCompanyAdmin]
    filterset_fields = ["channel", "status", "template_key"]

    def get_queryset(self):
        return NotificationOutbox.objects.filter(company=self.request.company)


class WorkerOTPRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        serializer = WorkerOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = Company.objects.filter(
            slug=serializer.validated_data["company_slug"], is_active=True
        ).first()
        challenge = None
        if company:
            challenge, notification, debug_code = create_worker_otp(
                company=company,
                phone=serializer.validated_data["phone"],
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            if notification:
                from .tasks import deliver_notification_task

                deliver_notification_task.delay(str(notification.id))
        data = {"detail": "If the number is registered, a verification code was sent."}
        data["challenge_id"] = challenge.id if challenge else uuid.uuid4()
        if challenge:
            if settings.DEBUG:
                data["debug_code"] = debug_code
        return Response(data, status=status.HTTP_202_ACCEPTED)


class WorkerOTPVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        serializer = WorkerOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, worker = verify_worker_otp(
            **serializer.validated_data,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.headers.get("User-Agent", ""),
        )
        return Response(
            {
                "token": token,
                "expires_in": 43200,
                "worker": {
                    "id": worker.id,
                    "name": worker.full_name,
                    "company": worker.company.name,
                },
            }
        )


class WhatsAppWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        if request.query_params.get("hub.mode") == "subscribe" and hmac.compare_digest(
            request.query_params.get("hub.verify_token", ""),
            settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
        ):
            return HttpResponse(
                request.query_params.get("hub.challenge", "0"),
                content_type="text/plain",
            )
        return Response({"detail": "Verification failed."}, status=403)

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = (
            "sha256="
            + hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        )
        signature_valid = bool(settings.WHATSAPP_APP_SECRET) and hmac.compare_digest(
            signature, expected
        )
        if not signature_valid:
            return Response({"detail": "Invalid webhook signature."}, status=403)
        payload = json.loads(raw_body)
        value = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
        message = value.get("messages", [{}])[0]
        event_id = message.get("id") or hashlib.sha256(raw_body).hexdigest()
        WhatsAppWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={"payload": payload, "signature_valid": True},
        )
        return Response({"status": "accepted"})
