from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import normalize_phone

from .models import ConsentRecord, Worker, WorkerDocument


class WorkerSerializer(serializers.ModelSerializer):
    payroll_ready = serializers.BooleanField(read_only=True)

    class Meta:
        model = Worker
        exclude = ["company"]
        read_only_fields = ["id", "created_at", "updated_at", "payroll_ready"]
        extra_kwargs = {
            "user_account": {"read_only": True},
            "bank_routing_code": {"write_only": True},
            "bank_account_or_card": {"write_only": True},
        }

    def validate(self, attrs):
        request = self.context["request"]
        worker_code = attrs.get(
            "worker_code", getattr(self.instance, "worker_code", "")
        ).strip()
        duplicate = Worker.objects.filter(
            company=request.company, worker_code__iexact=worker_code
        )
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"worker_code": "This worker code is already in use."}
            )
        attrs["worker_code"] = worker_code
        if "phone" in attrs:
            attrs["phone"] = normalize_phone(attrs["phone"]) if attrs["phone"] else ""
        for field in ("default_site",):
            value = attrs.get(field)
            if value and value.company_id != request.company.id:
                raise serializers.ValidationError({field: "Cross-company reference denied."})
        supervisor = attrs.get("supervisor")
        if (
            supervisor
            and not supervisor.memberships.filter(
                company=request.company, role="supervisor", is_active=True
            ).exists()
        ):
            raise serializers.ValidationError(
                {"supervisor": "An active company supervisor is required."}
            )
        start = attrs.get(
            "employment_start_date",
            getattr(self.instance, "employment_start_date", None),
        )
        end = attrs.get(
            "employment_end_date",
            getattr(self.instance, "employment_end_date", None),
        )
        if start and end and end < start:
            raise serializers.ValidationError(
                {"employment_end_date": "End date cannot be before the start date."}
            )
        status = attrs.get("status", getattr(self.instance, "status", Worker.Status.DRAFT))
        basic_wage = attrs.get(
            "basic_wage", getattr(self.instance, "basic_wage", 0)
        )
        default_site = attrs.get(
            "default_site", getattr(self.instance, "default_site", None)
        )
        selected_supervisor = attrs.get(
            "supervisor", getattr(self.instance, "supervisor", None)
        )
        if default_site and selected_supervisor:
            assigned = default_site.supervisor_links.filter(
                supervisor=selected_supervisor,
                active_from__lte=timezone.localdate(),
            ).filter(
                Q(active_until__isnull=True) | Q(active_until__gte=timezone.localdate())
            )
            if not assigned.exists():
                raise serializers.ValidationError(
                    {
                        "supervisor": (
                            "This supervisor is not currently assigned to the selected site."
                        )
                    }
                )
        category = attrs.get(
            "employment_category",
            getattr(self.instance, "employment_category", Worker.EmploymentCategory.SITE_WORKER),
        )
        if category == Worker.EmploymentCategory.STAFF:
            if attrs.get("wage_type", getattr(self.instance, "wage_type", None)) != (
                Worker.WageType.MONTHLY
            ):
                raise serializers.ValidationError(
                    {"wage_type": "Staff payroll profiles must use a monthly wage."}
                )
        if status == Worker.Status.ACTIVE:
            missing = []
            if basic_wage <= 0:
                missing.append("basic_wage")
            if category == Worker.EmploymentCategory.SITE_WORKER:
                if not default_site:
                    missing.append("default_site")
                if not selected_supervisor:
                    missing.append("supervisor")
            if missing:
                raise serializers.ValidationError(
                    {field: "Required before activating a worker." for field in missing}
                )
        return attrs


class WorkerDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerDocument
        exclude = ["company"]
        read_only_fields = ["id", "verified_at", "verified_by", "created_at", "updated_at"]
        extra_kwargs = {"reference_number": {"write_only": True}}

    def validate_worker(self, worker):
        if worker.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Cross-company reference denied.")
        return worker


class ConsentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        exclude = ["company"]
        read_only_fields = ["id", "captured_by", "created_at", "updated_at"]

    def validate_worker(self, worker):
        if worker.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Cross-company reference denied.")
        return worker
