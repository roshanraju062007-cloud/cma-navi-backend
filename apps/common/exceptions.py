from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Standardized DRF exception handler.
    Formats all API errors into a unified structure for the frontend:
    {
        "success": false,
        "error": {
            "code": "status_code_or_identifier",
            "message": "Short description",
            "details": {...}
        }
    }
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_details = response.data

        # Determine top-level message
        if isinstance(error_details, dict):
            message = error_details.get("detail", "An error occurred with your request.")
            # Remove redundant 'detail' key from details if present
            details = {k: v for k, v in error_details.items() if k != "detail"}
            if not details and "detail" in error_details:
                details = {"detail": error_details["detail"]}
        elif isinstance(error_details, list):
            message = error_details[0] if error_details else "Validation error."
            details = {"errors": error_details}
        else:
            message = str(error_details)
            details = {}

        formatted_data = {
            "success": False,
            "error": {
                "code": getattr(exc, "default_code", f"http_{response.status_code}"),
                "status_code": response.status_code,
                "message": str(message),
                "details": details,
            },
        }
        response.data = formatted_data
    else:
        logger.exception("Unhandled server exception: %s", exc)
        formatted_data = {
            "success": False,
            "error": {
                "code": "internal_server_error",
                "status_code": 500,
                "message": "An unexpected server error occurred.",
                "details": {},
            },
        }
        response = Response(formatted_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response
