from django.db import models
from apps.common.models import BaseModel

class TenantType(models.TextChoices):
    COLLEGE = "college", "College / University"
    MALL = "mall", "Shopping Mall"
    IT_PARK = "it_park", "IT / Corporate Park"
    OTHER = "other", "Other Facility"


class Tenant(BaseModel):
    """
    Tenant represents an isolated organization, campus, mall, or institution.
    All campus navigation data and visitor records are partitioned by tenant.
    """

    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    tenant_type = models.CharField(
        max_length=30, choices=TenantType.choices, default=TenantType.COLLEGE
    )
    domain = models.CharField(max_length=255, blank=True, null=True, unique=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_tenant_type_display()})"


class TenantScopedQuerySet(models.QuerySet):
    """Custom queryset providing helper methods for tenant-level isolation."""

    def for_tenant(self, tenant):
        """Filter queryset strictly to a specific tenant."""
        if tenant is None:
            return self.none()
        return self.filter(tenant=tenant)

    def for_user(self, user):
        """
        Filter queryset according to user privileges:
        - Super admins can access all records across all tenants.
        - Tenant members (admin, staff, security, user) are strictly scoped to their assigned tenant.
        """
        if not user or not user.is_authenticated:
            return self.none()
        if getattr(user, "is_super_admin", False) or user.is_superuser:
            return self.all()
        if user.tenant:
            return self.filter(tenant=user.tenant)
        return self.none()


class TenantScopedManager(models.Manager):
    """Manager that provides tenant-filtered queries."""

    def get_queryset(self):
        return TenantScopedQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)

    def for_user(self, user):
        return self.get_queryset().for_user(user)


class TenantScopedModel(BaseModel):
    """
    Abstract base model for all multi-tenant entities.
    Pradeesh (Campuses, Buildings, Floors, Blueprints, Nodes)
    and Bhuvaneshwari (Visitor Passes, Logs) will inherit from this class.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
    )

    objects = TenantScopedManager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
        ]
