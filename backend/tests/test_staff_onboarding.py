from datetime import date
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, User
from apps.payroll.models import PayrollCycle
from apps.payroll.services import build_payroll_lines
from apps.workforce.models import Worker


def authenticate(client, user, company, role):
    token = RefreshToken.for_user(user)
    token["company_id"] = str(company.id)
    token["role"] = role
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


@pytest.fixture
def admin(company):
    user = User.objects.create_user(
        phone="+971500009301", password="StrongTestPass!1", name="Company Admin"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.ADMIN)
    return user


def onboarding_payload(**overrides):
    payload = {
        "name": "New HR Officer",
        "phone": "+971500009302",
        "email": "hr@example.com",
        "preferred_language": "en",
        "role": "hr",
        "temporary_password": "A9!vQ2#kL7@zP4",
        "create_payroll_profile": True,
        "worker_code": "ST-001",
        "department": "Human Resources",
        "job_title": "HR Officer",
        "employment_start_date": "2026-06-01",
        "basic_wage": "6000.00",
        "allowances": [
            {"name": "Transport", "amount": "500.00", "frequency": "monthly"}
        ],
        "payroll_method": "bank",
        "bank_routing_code": "BANK-AE",
        "bank_account_or_card": "AE123456789",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_owner_onboards_hr_with_linked_payroll_profile(
    api_client, company, owner
):
    authenticate(api_client, owner, company, Membership.Role.OWNER)

    response = api_client.post(
        "/api/v1/memberships/onboard/",
        onboarding_payload(),
        format="json",
    )

    assert response.status_code == 201
    user = User.objects.get(phone="+971500009302")
    membership = Membership.objects.get(user=user, company=company)
    worker = Worker.objects.get(user_account=user, company=company)
    assert membership.role == Membership.Role.HR
    assert membership.invited_by == owner
    assert worker.employment_category == Worker.EmploymentCategory.STAFF
    assert worker.basic_wage == Decimal("6000.00")
    assert worker.department == "Human Resources"
    assert response.data["payroll_profile_id"] == str(worker.id)


@pytest.mark.django_db
def test_admin_cannot_grant_admin_or_owner_role(api_client, company, admin):
    authenticate(api_client, admin, company, Membership.Role.ADMIN)

    response = api_client.post(
        "/api/v1/memberships/onboard/",
        onboarding_payload(role="admin"),
        format="json",
    )

    assert response.status_code == 400
    assert not User.objects.filter(phone="+971500009302").exists()


@pytest.mark.django_db
def test_admin_cannot_modify_owner_membership(
    api_client, company, admin, owner
):
    authenticate(api_client, admin, company, Membership.Role.ADMIN)
    owner_membership = owner.memberships.get(company=company)

    response = api_client.patch(
        f"/api/v1/memberships/{owner_membership.id}/",
        {"is_active": False},
        format="json",
    )

    assert response.status_code == 403
    owner_membership.refresh_from_db()
    assert owner_membership.is_active is True


@pytest.mark.django_db
def test_last_owner_cannot_deactivate_their_membership(
    api_client, company, owner
):
    authenticate(api_client, owner, company, Membership.Role.OWNER)
    owner_membership = owner.memberships.get(company=company)

    response = api_client.delete(
        f"/api/v1/memberships/{owner_membership.id}/"
    )

    assert response.status_code == 400
    owner_membership.refresh_from_db()
    assert owner_membership.is_active is True


@pytest.mark.django_db
def test_owner_links_payroll_profile_to_existing_hr(
    api_client, company, owner
):
    hr = User.objects.create_user(
        phone="+971500009305", password="StrongTestPass!1", name="Existing HR"
    )
    membership = Membership.objects.create(
        user=hr,
        company=company,
        role=Membership.Role.HR,
    )
    authenticate(api_client, owner, company, Membership.Role.OWNER)

    response = api_client.post(
        f"/api/v1/memberships/{membership.id}/payroll-profile/",
        {
            "worker_code": "ST-EXISTING",
            "department": "Human Resources",
            "job_title": "HR Manager",
            "employment_start_date": "2026-06-01",
            "basic_wage": "8000.00",
            "allowances": [],
            "payroll_method": "bank",
            "bank_account_or_card": "AE-EXISTING",
        },
        format="json",
    )

    assert response.status_code == 201
    profile = Worker.objects.get(user_account=hr)
    assert profile.worker_code == "ST-EXISTING"
    assert profile.basic_wage == Decimal("8000.00")


@pytest.mark.django_db
def test_staff_payroll_uses_fixed_monthly_wage_without_attendance(
    company, owner
):
    staff = User.objects.create_user(
        phone="+971500009303", password="StrongTestPass!1", name="Finance Officer"
    )
    Membership.objects.create(
        user=staff,
        company=company,
        role=Membership.Role.FINANCE,
        invited_by=owner,
    )
    profile = Worker.objects.create(
        company=company,
        user_account=staff,
        employment_category=Worker.EmploymentCategory.STAFF,
        worker_code="ST-002",
        full_name=staff.name,
        phone=staff.phone,
        department="Finance",
        job_title="Finance Officer",
        employment_start_date=date(2026, 6, 1),
        status=Worker.Status.ACTIVE,
        wage_type=Worker.WageType.MONTHLY,
        basic_wage=Decimal("7000.00"),
        allowances=[
            {"name": "Transport", "amount": "500.00", "frequency": "monthly"}
        ],
        payroll_method="bank",
        bank_account_or_card="AE-STAFF",
    )
    cycle = PayrollCycle.objects.create(
        company=company,
        name="June 2026",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )

    build_payroll_lines(cycle, owner)

    line = cycle.lines.get(worker=profile)
    assert line.regular_pay == Decimal("7000.00")
    assert line.allowances == Decimal("500.00")
    assert line.gross_pay == Decimal("7500.00")
    assert line.net_pay == Decimal("7500.00")
    assert line.absence_deductions == Decimal("0")


@pytest.mark.django_db
def test_staff_wage_is_prorated_when_joining_mid_cycle(company, owner):
    profile = Worker.objects.create(
        company=company,
        employment_category=Worker.EmploymentCategory.STAFF,
        worker_code="ST-PRORATE",
        full_name="Mid-month Joiner",
        employment_start_date=date(2026, 6, 16),
        status=Worker.Status.ACTIVE,
        wage_type=Worker.WageType.MONTHLY,
        basic_wage=Decimal("6000.00"),
        allowances=[
            {"name": "Transport", "amount": "600.00", "frequency": "monthly"}
        ],
    )
    cycle = PayrollCycle.objects.create(
        company=company,
        name="June 2026",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )

    build_payroll_lines(cycle, owner)

    line = cycle.lines.get(worker=profile)
    assert line.regular_pay == Decimal("3000.00")
    assert line.allowances == Decimal("300.00")
    assert line.net_pay == Decimal("3300.00")


@pytest.mark.django_db
def test_staff_my_payroll_only_returns_own_locked_payslips(
    api_client, company, owner
):
    staff = User.objects.create_user(
        phone="+971500009304", password="StrongTestPass!1", name="HR Officer"
    )
    Membership.objects.create(user=staff, company=company, role=Membership.Role.HR)
    profile = Worker.objects.create(
        company=company,
        user_account=staff,
        employment_category=Worker.EmploymentCategory.STAFF,
        worker_code="ST-003",
        full_name=staff.name,
        phone=staff.phone,
        employment_start_date=date(2026, 6, 1),
        status=Worker.Status.ACTIVE,
        wage_type=Worker.WageType.MONTHLY,
        basic_wage=Decimal("6000.00"),
    )
    review_cycle = PayrollCycle.objects.create(
        company=company,
        name="June 2026",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )
    build_payroll_lines(review_cycle, owner)
    locked_cycle = PayrollCycle.objects.create(
        company=company,
        name="May 2026",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        status=PayrollCycle.Status.LOCKED,
    )
    locked_line = locked_cycle.lines.create(
        company=company,
        worker=profile,
        contract_basic=profile.basic_wage,
        regular_pay=profile.basic_wage,
        gross_pay=profile.basic_wage,
        calculated_net_pay=profile.basic_wage,
        net_pay=profile.basic_wage,
    )
    authenticate(api_client, staff, company, Membership.Role.HR)

    response = api_client.get("/api/v1/auth/my-payroll/")

    assert response.status_code == 200
    assert response.data["profile"]["worker_code"] == "ST-003"
    assert [line["id"] for line in response.data["payslips"]] == [str(locked_line.id)]
