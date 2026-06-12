from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class CompanyJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        company_id = token.get("company_id")
        if not company_id:
            raise AuthenticationFailed("Token has no active company.")
        membership = (
            user.memberships.select_related("company")
            .filter(company_id=company_id, is_active=True, company__is_active=True)
            .first()
        )
        if not membership:
            raise AuthenticationFailed("Company membership is inactive.")
        request.company = membership.company
        request.membership = membership
        return user, token
