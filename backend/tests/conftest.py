from datetime import date, time
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, User
from apps.organizations.models import Company, CompanyPolicy
from apps.sites.models import RosterAssignment, ShiftTemplate, Site, SiteSupervisor
from apps.workforce.models import Worker


@pytest.fixture
def company(db):
    company = Company.objects.create(
        name="Test Facilities",
        slug="test-facilities",
        legal_name="Test Facilities LLC",
    )
    CompanyPolicy.objects.create(company=company)
    return company


@pytest.fixture
def owner(company):
    user = User.objects.create_user(
        phone="+971500009001", password="StrongTestPass!1", name="Owner"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.OWNER)
    return user


@pytest.fixture
def supervisor(company):
    user = User.objects.create_user(
        phone="+971500009002", password="StrongTestPass!1", name="Supervisor"
    )
    Membership.objects.create(user=user, company=company, role=Membership.Role.SUPERVISOR)
    return user


@pytest.fixture
def site(company, supervisor):
    site = Site.objects.create(
        company=company,
        name="Test Site",
    )
    SiteSupervisor.objects.create(
        company=company,
        site=site,
        supervisor=supervisor,
        active_from=date.today(),
    )
    return site


@pytest.fixture
def shift(company):
    return ShiftTemplate.objects.create(
        company=company,
        name="Day",
        start_time=time(8),
        end_time=time(17),
        break_minutes=60,
    )


@pytest.fixture
def worker(company, supervisor, site):
    return Worker.objects.create(
        company=company,
        worker_code="W-1",
        full_name="Test Worker",
        employment_start_date=date(2025, 1, 1),
        status=Worker.Status.ACTIVE,
        wage_type=Worker.WageType.DAILY,
        basic_wage=Decimal("80"),
        payroll_method="card",
        bank_account_or_card="1234",
        default_site=site,
        supervisor=supervisor,
    )


@pytest.fixture
def roster(company, worker, site, shift, owner):
    return RosterAssignment.objects.create(
        company=company,
        worker=worker,
        site=site,
        shift=shift,
        date=date.today(),
        approved_by=owner,
    )


@pytest.fixture
def api_client():
    return APIClient()
