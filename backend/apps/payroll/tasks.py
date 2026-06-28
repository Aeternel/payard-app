import csv
import hashlib
import io

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.attendance.models import AttendanceRecord

from .models import PayrollExport
from .reports import build_report_artifact, report_data
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
    if export.export_type != "wps":
        raise ValueError("This task only handles WPS exports.")
    export.status = PayrollExport.Status.PROCESSING
    export.save(update_fields=["status", "updated_at"])
    try:
        content, filename, row_count = _build_wps_export(export)
        _save_completed_export(export=export, content=content, filename=filename, row_count=row_count)
        return str(export.id)
    except Exception as exc:
        _mark_export_failed(export=export, error=exc)
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3)
def generate_payroll_report(self, export_id):
    export = PayrollExport.objects.select_related("cycle", "company").get(pk=export_id)
    if export.export_type not in {"report_html", "report_pdf", "report_excel"}:
        raise ValueError("This task only handles payroll report artifacts.")
    export.status = PayrollExport.Status.PROCESSING
    export.save(update_fields=["status", "updated_at"])
    try:
        content, filename, row_count = _build_report_export(export)
        _save_completed_export(export=export, content=content, filename=filename, row_count=row_count)
        return str(export.id)
    except Exception as exc:
        _mark_export_failed(export=export, error=exc)
        raise self.retry(exc=exc) from exc


def _build_wps_export(export):
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
    rows = list(export.cycle.lines.select_related("worker").order_by("worker__worker_code"))
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
    filename = (
        f"payyard-wps-{export.cycle.period_start}-{export.cycle.period_end}"
        f"-v{export.version}.csv"
    )
    return output.getvalue().encode(), filename, len(rows)


def _build_report_export(export):
    report = report_data(export.cycle)
    report_format = export.export_type.removeprefix("report_")
    content, filename, _, _ = build_report_artifact(report, report_format)
    return content, filename, len(report.lines)


def _save_completed_export(*, export, content, filename, row_count):
    with transaction.atomic():
        export.file.save(filename, ContentFile(content), save=False)
        export.checksum = hashlib.sha256(content).hexdigest()
        export.row_count = row_count
        export.status = PayrollExport.Status.READY
        export.completed_at = timezone.now()
        export.error = ""
        export.save()


def _mark_export_failed(*, export, error):
    export.status = PayrollExport.Status.FAILED
    export.error = str(error)[:2000]
    export.save(update_fields=["status", "error", "updated_at"])
