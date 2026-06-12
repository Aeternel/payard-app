from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    DeviceViewSet,
    LoginView,
    MembershipViewSet,
    MeView,
    MyPayrollView,
    PasswordChangeView,
)
from apps.advances.views import AdvancePolicyViewSet, AdvanceRequestViewSet
from apps.attendance.views import (
    AttendanceExceptionViewSet,
    AttendanceRecordViewSet,
    OvertimeRequestViewSet,
)
from apps.compliance.views import ComplianceAlertViewSet
from apps.core.views import AuditLogViewSet, HealthView
from apps.disputes.views import (
    DisputeCommentViewSet,
    DisputeEvidenceViewSet,
    DisputeViewSet,
)
from apps.notifications.views import (
    NotificationOutboxViewSet,
    NotificationTemplateViewSet,
    WhatsAppWebhookView,
    WorkerOTPRequestView,
    WorkerOTPVerifyView,
)
from apps.organizations.views import (
    CompanyPolicyViewSet,
    CompanyViewSet,
    FeatureFlagViewSet,
    PayrollPolicyViewSet,
    WPSConfigurationViewSet,
)
from apps.payroll.views import (
    DailyWageLedgerViewSet,
    PayrollAdjustmentViewSet,
    PayrollCycleViewSet,
    PayrollExportViewSet,
    PayrollLineViewSet,
    WageRuleViewSet,
)
from apps.sites.views import (
    RosterAssignmentViewSet,
    ShiftTemplateViewSet,
    SiteSupervisorViewSet,
    SiteViewSet,
    WorkerTransferViewSet,
)
from apps.workforce.portal import (
    WorkerPortalAdvancesView,
    WorkerPortalAttendanceView,
    WorkerPortalDisputesView,
    WorkerPortalMeView,
    WorkerPortalPayslipsView,
    WorkerPortalWagesView,
)
from apps.workforce.views import (
    ConsentRecordViewSet,
    WorkerDocumentViewSet,
    WorkerViewSet,
)

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("company-policy", CompanyPolicyViewSet, basename="company-policy")
router.register("payroll-settings", PayrollPolicyViewSet, basename="payroll-settings")
router.register("wps-configuration", WPSConfigurationViewSet, basename="wps-configuration")
router.register("feature-flags", FeatureFlagViewSet)
router.register("memberships", MembershipViewSet, basename="membership")
router.register("devices", DeviceViewSet, basename="device")
router.register("workers", WorkerViewSet)
router.register("worker-documents", WorkerDocumentViewSet)
router.register("consents", ConsentRecordViewSet)
router.register("sites", SiteViewSet)
router.register("site-supervisors", SiteSupervisorViewSet)
router.register("shift-templates", ShiftTemplateViewSet)
router.register("rosters", RosterAssignmentViewSet)
router.register("worker-transfers", WorkerTransferViewSet)
router.register("attendance", AttendanceRecordViewSet, basename="attendance")
router.register(
    "attendance-exceptions", AttendanceExceptionViewSet, basename="attendance-exception"
)
router.register("overtime", OvertimeRequestViewSet)
router.register("wage-rules", WageRuleViewSet)
router.register("wage-ledger", DailyWageLedgerViewSet, basename="wage-ledger")
router.register("payroll-cycles", PayrollCycleViewSet)
router.register("payroll-lines", PayrollLineViewSet, basename="payroll-line")
router.register("payroll-adjustments", PayrollAdjustmentViewSet)
router.register("payroll-exports", PayrollExportViewSet, basename="payroll-export")
router.register("advance-policy", AdvancePolicyViewSet, basename="advance-policy")
router.register("advances", AdvanceRequestViewSet)
router.register("disputes", DisputeViewSet)
router.register("dispute-evidence", DisputeEvidenceViewSet)
router.register("dispute-comments", DisputeCommentViewSet)
router.register("compliance-alerts", ComplianceAlertViewSet, basename="compliance-alert")
router.register(
    "notification-templates", NotificationTemplateViewSet, basename="notification-template"
)
router.register("notification-outbox", NotificationOutboxViewSet, basename="notification-outbox")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", HealthView.as_view(), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/auth/login/", LoginView.as_view(), name="login"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/v1/auth/me/", MeView.as_view(), name="me"),
    path("api/v1/auth/my-payroll/", MyPayrollView.as_view(), name="my-payroll"),
    path("api/v1/auth/password/", PasswordChangeView.as_view(), name="password-change"),
    path("api/v1/worker-auth/request-otp/", WorkerOTPRequestView.as_view()),
    path("api/v1/worker-auth/verify-otp/", WorkerOTPVerifyView.as_view()),
    path("api/v1/worker/me/", WorkerPortalMeView.as_view()),
    path("api/v1/worker/attendance/", WorkerPortalAttendanceView.as_view()),
    path("api/v1/worker/wages/", WorkerPortalWagesView.as_view()),
    path("api/v1/worker/payslips/", WorkerPortalPayslipsView.as_view()),
    path("api/v1/worker/advances/", WorkerPortalAdvancesView.as_view()),
    path("api/v1/worker/disputes/", WorkerPortalDisputesView.as_view()),
    path("api/v1/webhooks/whatsapp/", WhatsAppWebhookView.as_view()),
    path("api/v1/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
