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
    """Serializer for registering a new user."""

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
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password fields do not match."}
            )

        tenant_id = attrs.get("tenant_id")
        role = attrs.get("role", UserRole.USER)

        # Non-super_admin users must be associated with a tenant
        if role != UserRole.SUPER_ADMIN and tenant_id:
            try:
                attrs["tenant"] = Tenant.objects.get(id=tenant_id, is_active=True)
            except Tenant.DoesNotExist:
                raise serializers.ValidationError(
                    {"tenant_id": "Specified tenant does not exist or is inactive."}
                )
        elif role != UserRole.SUPER_ADMIN and not tenant_id:
            # If registering a regular user without tenant_id, allowed as general visitor
            attrs["tenant"] = None
        else:
            attrs["tenant"] = None

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
