import csv
import hashlib
import io

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.attendance.models import AttendanceRecord

from .models import PayrollExport
from .services import calculate_attendance_wage


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def calculate_daily_wage(attendance_id):
    attendance = AttendanceRecord.objects.get(pk=attendance_id)
    ledger = calculate_attendance_wage(attendance)
    return str(ledger.id)


@shared_task(bind=True, max_retries=3)
def generate_wps_export(self, export_id):
    export = PayrollExport.objects.select_related("cycle", "company").get(pk=export_id)
    export.status = PayrollExport.Status.PROCESSING
    export.save(update_fields=["status", "updated_at"])
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "worker_code",
                "worker_name",
                "bank_routing_code",
                "account_or_card",
                "period_start",
                "period_end",
                "contract_basic",
                "variable_pay",
                "deductions",
                "net_pay",
                "employer_reference",
            ]
        )
        rows = export.cycle.lines.select_related("worker").order_by("worker__worker_code")
        for line in rows:
            worker = line.worker
            writer.writerow(
                [
                    worker.worker_code,
                    worker.full_name,
                    worker.bank_routing_code,
                    worker.bank_account_or_card,
                    export.cycle.period_start,
                    export.cycle.period_end,
                    line.contract_basic,
                    line.overtime_pay + line.allowances + line.other_earnings,
                    line.absence_deductions + line.advance_deductions + line.other_deductions,
                    line.net_pay,
                    line.employer_reference,
                ]
            )
        content = output.getvalue().encode()
        filename = (
            f"payyard-wps-{export.cycle.period_start}-{export.cycle.period_end}"
            f"-v{export.version}.csv"
        )
        with transaction.atomic():
            export.file.save(filename, ContentFile(content), save=False)
            export.checksum = hashlib.sha256(content).hexdigest()
            export.row_count = rows.count()
            export.status = PayrollExport.Status.READY
            export.completed_at = timezone.now()
            export.error = ""
            export.save()
        return str(export.id)
    except Exception as exc:
        export.status = PayrollExport.Status.FAILED
        export.error = str(exc)[:2000]
        export.save(update_fields=["status", "error", "updated_at"])
        raise self.retry(exc=exc) from exc
