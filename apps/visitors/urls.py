from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VisitorPassViewSet,
    VisitorLogViewSet,
    verify_qr_view,
    check_in_view,
    check_out_view,
)

router = DefaultRouter()
router.register(r"passes", VisitorPassViewSet, basename="visitor-pass")
router.register(r"logs", VisitorLogViewSet, basename="visitor-log")

urlpatterns = [
    # Dedicated QR and Gate Security endpoints
    path("verify-qr/", verify_qr_view, name="visitor-verify-qr"),
    path("check-in/", check_in_view, name="visitor-check-in"),
    path("check-out/", check_out_view, name="visitor-check-out"),
    # REST ViewSets
    path("", include(router.urls)),
]
