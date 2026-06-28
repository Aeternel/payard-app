from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.notifications.models import WorkerOTPChallenge
from apps.organizations.models import Company


@pytest.mark.django_db
def test_login_resolves_company_from_phone_and_password(api_client, owner, company):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"phone": owner.phone, "password": "StrongTestPass!1"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["company"]["id"] == str(company.id)
    assert response.data["company"]["slug"] == company.slug
    assert response.data["role"] == Membership.Role.OWNER
    assert response.data["access"]
    assert response.data["refresh"]


@pytest.mark.django_db
def test_login_rejects_user_without_active_company(api_client, owner, company):
    membership = owner.memberships.get(company=company)
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])

    response = api_client.post(
        "/api/v1/auth/login/",
        {"phone": owner.phone, "password": "StrongTestPass!1"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["detail"]["non_field_errors"] == [
        "Your account has no active company access."
    ]


@pytest.mark.django_db
def test_login_fails_closed_for_multiple_active_companies(api_client, owner):
    other_company = Company.objects.create(
        name="Other Facilities",
        slug="other-facilities",
        legal_name="Other Facilities LLC",
    )
    Membership.objects.create(
        user=owner,
        company=other_company,
        role=Membership.Role.ADMIN,
    )

    response = api_client.post(
        "/api/v1/auth/login/",
        {"phone": owner.phone, "password": "StrongTestPass!1"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["detail"]["non_field_errors"] == [
        "Your account has multiple active company memberships. "
        "Contact an administrator to keep one active login membership."
    ]


@pytest.mark.django_db
def test_login_rejects_invalid_password_without_company_lookup(api_client, owner):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"phone": owner.phone, "password": "not-the-password"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["detail"]["non_field_errors"] == [
        "Invalid phone or password."
    ]


@pytest.mark.django_db
def test_worker_otp_request_stays_generic_when_registered_number_is_rate_limited(
    api_client, company, worker
):
    worker.phone = "+971500001001"
    worker.save(update_fields=["phone", "updated_at"])
    for _ in range(3):
        WorkerOTPChallenge.objects.create(
            company=company,
            worker=worker,
            code_hash="hash",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    registered_response = api_client.post(
        "/api/v1/worker-auth/request-otp/",
        {"company_slug": company.slug, "phone": worker.phone},
        format="json",
    )
    unknown_response = api_client.post(
        "/api/v1/worker-auth/request-otp/",
        {"company_slug": company.slug, "phone": "+971500009999"},
        format="json",
    )

    assert registered_response.status_code == 202
    assert unknown_response.status_code == 202
    assert registered_response.data["detail"] == unknown_response.data["detail"]
    assert "challenge_id" in registered_response.data
    assert WorkerOTPChallenge.objects.filter(company=company, worker=worker).count() == 3
