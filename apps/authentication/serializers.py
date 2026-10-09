from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from apps.tenants.models import Tenant
from apps.tenants.serializers import TenantSummarySerializer
from .models import User, UserRole

class UserSerializer(serializers.ModelSerializer):
    """Detailed serializer for user representation."""

    tenant = TenantSummarySerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "role",
            "tenant",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "is_active",
        ]


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for public self-registration.
    SECURITY HARDENED:
    - Strictly creates only standard 'user' role accounts.
    - Never accepts or honors client-supplied 'role' or 'tenant_id'.
    - New accounts are initialized without tenant association until explicitly
      assigned by an authorized tenant administrator.
    """

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password fields do not match."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        # Ensure client cannot pass 'role' or 'tenant' under any circumstance
        validated_data.pop("role", None)
        validated_data.pop("tenant", None)
        validated_data.pop("tenant_id", None)
        password = validated_data.pop("password")

        user = User.objects.create_user(
            password=password,
            role=UserRole.USER,
            tenant=None,
            **validated_data,
        )
        return user


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for administrative user creation.
    Only accessible by authorized administrators (Tenant Admin and Super Admin).
    Enforces strict role assignment boundaries:
    - Tenant Admins can only create staff, security, or regular users within their own tenant.
    - Super Admins can create any role across any tenant.
    """

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)
    tenant_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "tenant_id",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        requester = request.user
        role = attrs.get("role", UserRole.USER)
        tenant_id = attrs.get("tenant_id")

        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password fields do not match."}
            )

        if requester.is_super_admin:
            # Super Admin can assign any tenant
            if tenant_id:
                try:
                    attrs["tenant"] = Tenant.objects.get(id=tenant_id, is_active=True)
                except Tenant.DoesNotExist:
                    raise serializers.ValidationError(
                        {"tenant_id": "Specified tenant does not exist or is inactive."}
                    )
            else:
                attrs["tenant"] = None
        elif requester.is_tenant_admin:
            # Tenant Admin cannot create super_admin or tenant_admin
            if role in [UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN]:
                raise serializers.ValidationError(
                    {"role": "Tenant administrators cannot create administrative accounts."}
                )
            # Tenant Admin must bind new user strictly to their own tenant
            attrs["tenant"] = requester.tenant
        else:
            raise serializers.ValidationError(
                "You do not have permission to create users via this endpoint."
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        validated_data.pop("tenant_id", None)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT login serializer that enriches token response
    with user profile, role, and tenant details for the TypeScript frontend.
    """

    username_field = "email"

    def validate(self, attrs):
        data = super().validate(attrs)

        data["user"] = {
            "id": str(self.user.id),
            "email": self.user.email,
            "full_name": self.user.get_full_name(),
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "role": self.user.role,
            "tenant": (
                {
                    "id": str(self.user.tenant.id),
                    "name": self.user.tenant.name,
                    "slug": self.user.tenant.slug,
                    "tenant_type": self.user.tenant.tenant_type,
                }
                if self.user.tenant
                else None
            ),
        }
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for authenticated password changes."""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "New password fields do not match."}
            )
        return attrs


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user's personal profile information."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number"]
