from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

def health_check(request):
    """System health check endpoint."""
    return JsonResponse(
        {
            "status": "healthy",
            "service": "wayora-backend",
            "version": "1.0.0",
        }
    )

api_v1_patterns = [
    path("auth/", include("apps.authentication.urls")),
    path("tenants/", include("apps.tenants.urls")),
    path("blueprints/", include("apps.blueprints.urls")),
    path("health/", health_check, name="api-v1-health"),
    # OpenAPI Schema & Interactive Documentation
    path("schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="openapi-schema"),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="openapi-schema"),
        name="redoc-ui",
    ),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("api/v1/", include(api_v1_patterns)),
]
