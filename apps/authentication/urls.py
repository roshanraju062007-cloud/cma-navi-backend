from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    CurrentUserView,
    ChangePasswordView,
    UserManagementViewSet,
)

router = DefaultRouter()
router.register(r"users", UserManagementViewSet, basename="user-management")

urlpatterns = [
    # Auth endpoints
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", CustomTokenObtainPairView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    # User management
    path("", include(router.urls)),
]
