from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BlueprintViewSet,
    local_storage_upload_view,
    local_storage_download_view,
)

router = DefaultRouter()
router.register(r"", BlueprintViewSet, basename="blueprint")

urlpatterns = [
    # Local development private storage handlers
    path("storage/upload/", local_storage_upload_view, name="blueprint-storage-upload"),
    path("storage/download/", local_storage_download_view, name="blueprint-storage-download"),
    # REST API endpoints
    path("", include(router.urls)),
]
