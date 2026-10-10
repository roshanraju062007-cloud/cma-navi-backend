from rest_framework import permissions
from apps.authentication.models import UserRole


class IsSecurityOrAdmin(permissions.BasePermission):
    """
    Permission check granting access to Security personnel, Tenant Admins, or Super Admins.
    Used for QR validation and gate check-in / check-out operations.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return bool(
            getattr(user, "is_super_admin", False)
            or user.is_superuser
            or getattr(user, "is_tenant_admin", False)
            or getattr(user, "is_security", False)
        )


class CanAccessVisitorPass(permissions.BasePermission):
    """
    Object-level permission for visitor passes:
    - Super admins have full access across tenants.
    - Tenant admins have full access within their tenant.
    - Security personnel can view and verify passes within their tenant.
    - Host staff can view, approve, reject, and cancel passes assigned to them.
    - Creators (e.g. users who requested a pass) can view and cancel their pending passes.
    - Cross-tenant access is strictly denied.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Super admin global override
        if getattr(user, "is_super_admin", False) or user.is_superuser:
            return True

        # Strict tenant boundary check
        if user.tenant != obj.tenant:
            return False

        # Tenant admin has full management privileges within their tenant
        if getattr(user, "is_tenant_admin", False):
            return True

        # Security personnel can view and scan passes within their tenant
        if getattr(user, "is_security", False):
            return True

        # Host has full view and decision authority on passes where they are host
        if obj.host == user:
            return True

        # Pass creator can view their pass and cancel if pending
        if obj.created_by == user:
            if view.action in ["retrieve", "cancel"]:
                return True

        return False


class CanApproveOrRejectPass(permissions.BasePermission):
    """
    Only designated Host of the pass, Tenant Admin, or Super Admin can approve or reject a pass.
    Security users or unrelated users cannot approve passes.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if getattr(user, "is_super_admin", False) or user.is_superuser:
            return True

        if user.tenant != obj.tenant:
            return False

        if getattr(user, "is_tenant_admin", False):
            return True

        # Staff host can approve/reject their own hosted passes
        if obj.host == user:
            return True

        return False
