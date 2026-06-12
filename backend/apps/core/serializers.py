from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.name", read_only=True)

    class Meta:
        model = AuditLog
        fields = "__all__"
        read_only_fields = [field.name for field in AuditLog._meta.fields]
