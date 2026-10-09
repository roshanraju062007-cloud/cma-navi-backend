import uuid
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from apps.common.models import TimeStampedModel

class UserRole(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super Admin"
    TENANT_ADMIN = "tenant_admin", "Tenant Admin"
    STAFF = "staff", "Staff / Faculty"
    SECURITY = "security", "Security Personnel"
    USER = "user", "General User / Visitor"


class UserManager(BaseUserManager):
    """Manager for custom Wayora User model with email authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address must be provided.")
        email = self.normalize_email(email)
        extra_fields.setdefault("role", UserRole.USER)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.SUPER_ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Wayora custom user entity.
    Uses email as the primary unique identifier and supports multi-tenant roles:
    - super_admin
    - tenant_admin
    - staff
    - security
    - user
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.USER,
        db_index=True,
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
        help_text="Tenant organization this user belongs to. Null for super_admin.",
        db_index=True,
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into the Django admin site.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this user account should be considered active.",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "role"]),
            models.Index(fields=["tenant", "role"]),
        ]

    def __str__(self):
        full_name = self.get_full_name()
        return f"{full_name} ({self.email}) [{self.role}]" if full_name else f"{self.email} [{self.role}]"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name or self.email

    @property
    def is_super_admin(self):
        return self.role == UserRole.SUPER_ADMIN or self.is_superuser

    @property
    def is_tenant_admin(self):
        return self.role == UserRole.TENANT_ADMIN

    @property
    def is_staff_member(self):
        return self.role == UserRole.STAFF

    @property
    def is_security(self):
        return self.role == UserRole.SECURITY

    @property
    def is_regular_user(self):
        return self.role == UserRole.USER
