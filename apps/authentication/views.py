from rest_framework import generics, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema, extend_schema_view
from .models import User, UserRole
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    AdminUserCreateSerializer,
    CustomTokenObtainPairSerializer,
    ChangePasswordSerializer,
    UserProfileUpdateSerializer,
)
from .permissions import IsSuperAdmin, IsTenantAdmin, CanManageUser

@extend_schema(
    summary="Register a new user account",
    description="Registers a new standard user account. Privileged roles and tenant memberships are assigned exclusively through authorized administrative workflows.",
    responses={201: UserSerializer},
)
class RegisterView(generics.CreateAPIView):
    """User registration endpoint open to public registrations."""

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        output_serializer = UserSerializer(user)
        return Response(
            {
                "success": True,
                "message": "User registered successfully.",
                "user": output_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="User login with JWT authentication",
    description="Authenticates credentials and returns JWT access/refresh tokens alongside user role and tenant context.",
)
class CustomTokenObtainPairView(TokenObtainPairView):
    """JWT Token obtain view returning access, refresh, and user payload."""

    serializer_class = CustomTokenObtainPairSerializer


class CurrentUserView(APIView):
    """View to get or update the authenticated user's profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current authenticated user profile",
        responses={200: UserSerializer},
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({"success": True, "user": serializer.data})

    @extend_schema(
        summary="Update current authenticated user profile",
        request=UserProfileUpdateSerializer,
        responses={200: UserSerializer},
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "user": UserSerializer(request.user).data})


class ChangePasswordView(APIView):
    """View to change authenticated user's password."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change user password",
        request=ChangePasswordSerializer,
        responses={200: dict},
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "invalid_old_password",
                        "status_code": 400,
                        "message": "Current password is incorrect.",
                        "details": {},
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"success": True, "message": "Password changed successfully."})


@extend_schema_view(
    list=extend_schema(summary="List users (scoped to tenant unless Super Admin)"),
    retrieve=extend_schema(summary="Retrieve user details"),
    create=extend_schema(summary="Create a user under tenant (Admin only)"),
    update=extend_schema(summary="Update a user"),
    partial_update=extend_schema(summary="Partially update a user"),
    destroy=extend_schema(summary="Deactivate or remove a user"),
)
class UserManagementViewSet(viewsets.ModelViewSet):
    """
    User management for administrators.
    - Super admins can manage all users across all tenants.
    - Tenant admins can manage users (staff, security, regular) within their assigned tenant.
    """

    queryset = User.objects.all()
    permission_classes = [IsAuthenticated, CanManageUser]

    def get_serializer_class(self):
        if self.action == "create":
            return AdminUserCreateSerializer
        return UserSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return User.objects.none()
        if getattr(user, "is_super_admin", False) or user.is_superuser:
            return User.objects.all().select_related("tenant")
        if user.tenant:
            return User.objects.filter(tenant=user.tenant).select_related("tenant")
        return User.objects.filter(id=user.id)
