from django.db import transaction
from rest_framework import viewsets

from .permissions import HasActiveCompany
from .services import model_snapshot, record_audit


class TenantModelViewSet(viewsets.ModelViewSet):
    permission_classes = [HasActiveCompany]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        queryset = queryset.filter(company=self.request.company)
        if getattr(self.request.membership, "role", None) == "supervisor":
            queryset = self.scope_supervisor_queryset(queryset)
        return queryset

    def scope_supervisor_queryset(self, queryset):
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(company=self.request.company)
        record_audit(instance=instance, action="created", actor=self.request.user)

    @transaction.atomic
    def perform_update(self, serializer):
        before = model_snapshot(self.get_object())
        instance = serializer.save()
        record_audit(
            instance=instance,
            action="updated",
            actor=self.request.user,
            before=before,
        )

    def perform_destroy(self, instance):
        before = model_snapshot(instance)
        instance.delete()
        record_audit(
            instance=instance,
            action="deleted",
            actor=self.request.user,
            before=before,
            after={},
        )
