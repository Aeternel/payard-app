from rest_framework import serializers

from .models import NotificationOutbox, NotificationTemplate


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationOutboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationOutbox
        exclude = ["company"]
        read_only_fields = [
            field.name for field in NotificationOutbox._meta.fields if field.name != "company"
        ]


class WorkerOTPRequestSerializer(serializers.Serializer):
    company_slug = serializers.SlugField()
    phone = serializers.CharField(max_length=20)


class WorkerOTPVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.RegexField(r"^\d{6}$")
