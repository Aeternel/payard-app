from datetime import date
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, User
from apps.workforce.models import Worker


def authenticate(client, user, company, role):
    token = RefreshToken.for_user(user)
    token["company_id"] = str(company.id)
    token["role"] = role
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


@pytest.fixture
def hr(company):
    user = User.objects.create_user(
        phone="+971500009103", password="StrongTestPass!1", name="HR Manager"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.HR)
    return user


@pytest.mark.django_db
def test_hr_can_create_active_worker(
    api_client, company, hr, supervisor, site
):
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.post(
        "/api/v1/workers/",
        {
            "worker_code": "W-NEW",
            "full_name": "New Worker",
            "phone": "+971 50 123 4567",
            "nationality": "Nepal",
            "preferred_language": "en",
            "notification_channel": "whatsapp",
            "job_title": "Cleaner",
            "employment_start_date": str(date.today()),
            "status": "active",
            "wage_type": "monthly",
            "basic_wage": "1500.00",
            "allowances": [{"name": "Food", "amount": "300.00", "frequency": "monthly"}],
            "payroll_method": "card",
            "bank_account_or_card": "CARD-10001",
            "default_site": str(site.id),
            "supervisor": str(supervisor.id),
        },
        format="json",
    )

    assert response.status_code == 201
    worker = Worker.objects.get(company=company, worker_code="W-NEW")
    assert worker.status == Worker.Status.ACTIVE
    assert worker.basic_wage == Decimal("1500.00")
    assert worker.default_site == site
    assert worker.supervisor == supervisor
    assert worker.phone == "+971501234567"


@pytest.mark.django_db
def test_supervisor_cannot_create_worker(
    api_client, company, supervisor, site
):
    authenticate(api_client, supervisor, company, Membership.Role.SUPERVISOR)

    response = api_client.post(
        "/api/v1/workers/",
        {
            "worker_code": "W-DENIED",
            "full_name": "Denied Worker",
            "employment_start_date": str(date.today()),
            "status": "active",
            "wage_type": "daily",
            "basic_wage": "80.00",
            "default_site": str(site.id),
            "supervisor": str(supervisor.id),
        },
        format="json",
    )

    assert response.status_code == 403
    assert not Worker.objects.filter(company=company, worker_code="W-DENIED").exists()


@pytest.mark.django_db
def test_active_worker_requires_site_and_supervisor(api_client, company, hr):
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.post(
        "/api/v1/workers/",
        {
            "worker_code": "W-INCOMPLETE",
            "full_name": "Incomplete Worker",
            "employment_start_date": str(date.today()),
            "status": "active",
            "wage_type": "monthly",
            "basic_wage": "1500.00",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "default_site" in response.data["error"]["detail"]
    assert "supervisor" in response.data["error"]["detail"]


@pytest.mark.django_db
def test_hr_creation_options_only_include_company_resources(
    api_client, company, hr, supervisor, site
):
    authenticate(api_client, hr, company, Membership.Role.HR)

    response = api_client.get("/api/v1/workers/creation-options/")

    assert response.status_code == 200
    assert response.data["sites"] == [
        {"id": str(site.id), "name": site.name, "address": site.address}
    ]
    assert response.data["supervisors"] == [
        {
            "id": str(supervisor.id),
            "name": supervisor.name,
            "phone": supervisor.phone,
            "site_ids": [str(site.id)],
        }
    ]
