from apps.sites.models import Site
from apps.workforce.models import Worker


def setup_readiness(company):
    checks = {
        "company_legal_name": bool(company.legal_name),
        "company_trade_license": bool(company.trade_license_number),
        "company_policy": hasattr(company, "policy"),
        "active_wps_configuration": hasattr(company, "wps_configuration")
        and company.wps_configuration.is_active,
        "at_least_one_site": Site.objects.filter(company=company, is_active=True).exists(),
        "all_active_workers_payroll_ready": not Worker.objects.filter(
            company=company, status=Worker.Status.ACTIVE
        )
        .filter(basic_wage__lte=0)
        .exists(),
    }
    completed = sum(checks.values())
    return {
        "score": round(completed / len(checks) * 100),
        "checks": checks,
        "blockers": [key for key, passed in checks.items() if not passed],
    }
