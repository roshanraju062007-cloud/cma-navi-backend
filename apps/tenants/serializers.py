from rest_framework import serializers
from .models import Tenant

class TenantSerializer(serializers.ModelSerializer):
    """Serializer for tenant listings and creation."""

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "tenant_type",
            "domain",
            "contact_email",
            "contact_phone",
            "address",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantSummarySerializer(serializers.ModelSerializer):
    """Compact tenant serializer for nested relationships."""

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "tenant_type"]
        read_only_fields = fields
