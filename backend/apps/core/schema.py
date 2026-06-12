from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CompanyJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.core.authentication.CompanyJWTAuthentication"
    name = "staffJwt"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Staff access token scoped to one active company.",
        }


class WorkerPortalAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.notifications.authentication.WorkerPortalAuthentication"
    name = "workerSession"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Use `Worker <opaque-session-token>`.",
        }
