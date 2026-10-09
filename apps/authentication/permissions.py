from rest_framework import permissions
from .models import UserRole

class IsSuperAdmin(permissions.BasePermission):
    """Permission check for platform super administrators."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_super_admin", False)
        )


class IsTenantAdmin(permissions.BasePermission):
    """Permission check for tenant administrators or super administrators."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return bool(
            getattr(request.user, "is_super_admin", False)
            or getattr(request.user, "is_tenant_admin", False)
        )


class IsStaffUser(permissions.BasePermission):
    """Permission check for staff members, tenant admins, or super admins."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return bool(
            getattr(request.user, "is_super_admin", False)
            or getattr(request.user, "is_tenant_admin", False)
            or getattr(request.user, "is_staff_member", False)
        )


class IsSecurityUser(permissions.BasePermission):
    """Permission check for security personnel, tenant admins, or super admins."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return bool(
            getattr(request.user, "is_super_admin", False)
            or getattr(request.user, "is_tenant_admin", False)
            or getattr(request.user, "is_security", False)
        )


class IsStaffOrSecurity(permissions.BasePermission):
    """Permission check for either staff or security personnel within a tenant."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return bool(
            getattr(request.user, "is_super_admin", False)
            or getattr(request.user, "is_tenant_admin", False)
            or getattr(request.user, "is_staff_member", False)
            or getattr(request.user, "is_security", False)
        )


class CanManageUser(permissions.BasePermission):
    """
    Role-based user management access control:
    - Super Admin can list, create, view, update, and delete any user across all tenants.
    - Tenant Admin can list and create users within their own tenant (staff, security, user only),
      and view/update those users. Tenant Admin cannot modify Super Admins or other Tenant Admins.
    - Regular users cannot list or create users, and can only view/update their own profile.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        # Listing and creation require at least Tenant Admin privileges
        if view.action in ["list", "create"]:
            return bool(
                getattr(request.user, "is_super_admin", False)
                or getattr(request.user, "is_tenant_admin", False)
            )

        # Detail actions (retrieve, update, partial_update, destroy) proceed to has_object_permission
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Super Admin has global management authority
        if user.is_super_admin:
            return True

        # Tenant Admin can manage non-administrative users within their own tenant
        if user.is_tenant_admin and obj.tenant == user.tenant:
            # Tenant Admin cannot modify or delete Super Admins or other Tenant Admins
            if obj.role in [UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN] and obj != user:
                return False
            return True

        # Ordinary users can only view or update their own profile, never delete or manage others
        if obj == user:
            return request.method in ["GET", "PUT", "PATCH"]

        return False
