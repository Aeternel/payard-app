from rest_framework.permissions import BasePermission

ROLE_RANK = {
    "supervisor": 10,
    "operations": 20,
    "hr": 30,
    "payroll": 40,
    "finance": 50,
    "admin": 80,
    "owner": 100,
}


class HasActiveCompany(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "company", None)
            and getattr(request, "membership", None)
        )


class RoleAtLeast(BasePermission):
    minimum_role = "supervisor"

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return bool(
            membership and ROLE_RANK.get(membership.role, 0) >= ROLE_RANK.get(self.minimum_role, 0)
        )


class RoleIn(BasePermission):
    allowed_roles = frozenset()

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return bool(membership and membership.role in self.allowed_roles)


class IsCompanyAdmin(RoleAtLeast):
    minimum_role = "admin"


class IsPayrollOperator(RoleAtLeast):
    minimum_role = "payroll"


class IsFinanceApprover(RoleAtLeast):
    minimum_role = "finance"


class CanViewPayroll(RoleIn):
    allowed_roles = {"hr", "payroll", "finance", "admin", "owner"}


class IsPayrollManager(RoleIn):
    allowed_roles = {"hr", "admin", "owner"}


class CanBuildPayroll(RoleIn):
    allowed_roles = {"hr", "payroll", "finance", "admin", "owner"}


class IsWorkforceManager(RoleIn):
    allowed_roles = {"hr", "admin", "owner"}


class CanCreateDisputes(RoleIn):
    allowed_roles = {"supervisor", "operations", "hr", "admin", "owner"}


class IsDisputeResolver(RoleIn):
    allowed_roles = {"hr", "admin", "owner"}


class IsAdvanceDisburser(RoleIn):
    allowed_roles = {"finance", "admin", "owner"}


class CanManageAttendance(RoleIn):
    allowed_roles = {"supervisor", "operations", "hr", "payroll", "admin", "owner"}


class CanManageSiteOperations(RoleIn):
    allowed_roles = {"operations", "hr", "admin", "owner"}


class CanResolveCompliance(RoleIn):
    allowed_roles = {"operations", "hr", "admin", "owner"}
