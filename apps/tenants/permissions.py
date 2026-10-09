from rest_framework import permissions

class IsSuperAdmin(permissions.BasePermission):
    """Allows access only to global super admins."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (getattr(request.user, "is_super_admin", False) or request.user.is_superuser)
        )


class IsTenantAdmin(permissions.BasePermission):
    """Allows access to tenant admins and global super admins."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return bool(
            getattr(request.user, "is_super_admin", False)
            or getattr(request.user, "is_tenant_admin", False)
            or request.user.is_superuser
        )

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, "is_super_admin", False) or request.user.is_superuser:
            return True
        tenant = getattr(obj, "tenant", obj if hasattr(obj, "slug") else None)
        return request.user.tenant == tenant


class IsTenantMember(permissions.BasePermission):
    """
    Enforces tenant data isolation at the object level.
    Ensures that a user can only access resources belonging to their assigned tenant.
    Super admins have global override access.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if getattr(request.user, "is_super_admin", False) or request.user.is_superuser:
            return True
        return bool(request.user.tenant and request.user.tenant.is_active)

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, "is_super_admin", False) or request.user.is_superuser:
            return True
        tenant = getattr(obj, "tenant", None)
        if tenant is None and hasattr(obj, "slug"):
            # The object itself is a Tenant instance
            return request.user.tenant == obj
        return request.user.tenant == tenant
