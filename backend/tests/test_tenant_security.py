import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, User
from apps.organizations.models import Company


@pytest.mark.django_db
def test_worker_list_is_tenant_scoped(api_client, owner, company, worker):
    other = Company.objects.create(name="Other", slug="other", legal_name="Other LLC")
    other_user = User.objects.create_user(
        phone="+971500009099", password="StrongTestPass!1", name="Other Owner"
    )
    Membership.objects.create(user=other_user, company=other, role=Membership.Role.OWNER)
    token = RefreshToken.for_user(owner)
    token["company_id"] = str(company.id)
    token["role"] = "owner"
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    response = api_client.get("/api/v1/workers/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(worker.id)


@pytest.mark.django_db
def test_token_for_inactive_membership_is_rejected(api_client, owner, company):
    membership = owner.memberships.get(company=company)
    membership.is_active = False
    membership.save()
    token = RefreshToken.for_user(owner)
    token["company_id"] = str(company.id)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    response = api_client.get("/api/v1/workers/")
    assert response.status_code == 401
