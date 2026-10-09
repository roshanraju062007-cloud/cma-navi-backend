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
    Super Admin can manage any user.
    Tenant Admin can manage users (staff, security, user) within their own tenant.
    Users can manage their own profile.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_super_admin:
            return True
        if user.is_tenant_admin and obj.tenant == user.tenant:
            # Tenant admin cannot promote anyone to super_admin or modify other tenant admins
            return obj.role != UserRole.SUPER_ADMIN
        return obj == user
