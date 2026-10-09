from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view
from .models import Tenant
from .serializers import TenantSerializer
from .permissions import IsSuperAdmin, IsTenantAdmin

@extend_schema_view(
    list=extend_schema(summary="List tenants (Super Admin: all; Tenant Admin: own tenant)"),
    create=extend_schema(summary="Create a new tenant (Super Admin only)"),
    retrieve=extend_schema(summary="Retrieve tenant details"),
    update=extend_schema(summary="Update tenant details"),
    partial_update=extend_schema(summary="Partially update tenant details"),
    destroy=extend_schema(summary="Deactivate or delete a tenant (Super Admin only)"),
)
class TenantViewSet(viewsets.ModelViewSet):
    """
    Endpoints for managing tenants (campuses, colleges, malls, IT parks).
    Super Admins can manage all tenants.
    Tenant Admins can only view and edit their own tenant organization.
    """

    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer

    def get_permissions(self):
        if self.action in ["create", "destroy"]:
            permission_classes = [IsSuperAdmin]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [IsTenantAdmin]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Tenant.objects.none()
        if getattr(user, "is_super_admin", False) or user.is_superuser:
            return Tenant.objects.all()
        if user.tenant:
            return Tenant.objects.filter(id=user.tenant_id)
        return Tenant.objects.none()

    @extend_schema(
        summary="Get details for current user's tenant organization",
        responses={200: TenantSerializer},
    )
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def current(self, request):
        """Returns the tenant organization for the current authenticated user."""
        if not request.user.tenant:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "no_tenant_assigned",
                        "status_code": 404,
                        "message": "User is not associated with any tenant organization.",
                        "details": {},
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(request.user.tenant)
        return Response({"success": True, "tenant": serializer.data})
