from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response
    request = context.get("request")
    response.data = {
        "error": {
            "code": getattr(exc, "default_code", "api_error"),
            "detail": response.data,
            "request_id": str(getattr(request, "request_id", "")),
        }
    }
    return response
