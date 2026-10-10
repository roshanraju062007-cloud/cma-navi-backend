from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.tenants.models import Tenant
from .models import VisitorPass, VisitorLog, PassStatus, LogAction

User = get_user_model()


class HostBriefSerializer(serializers.ModelSerializer):
    """Brief representation of a host user."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "phone_number", "role"]
        read_only_fields = fields


class VisitorPassCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for requesting a visitor pass.
    Enforces tenant boundaries on host and visitor fields.
    """

    host_id = serializers.UUIDField(write_only=True, required=True)
    tenant_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = VisitorPass
        fields = [
            "id",
            "host_id",
            "tenant_id",
            "visitor_name",
            "visitor_email",
            "visitor_phone",
            "purpose",
            "valid_from",
            "valid_until",
            "notes",
            "status",
            "qr_token",
            "created_at",
        ]
        read_only_fields = ["id", "status", "qr_token", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        # Determine target tenant
        if user and (getattr(user, "is_super_admin", False) or user.is_superuser):
            tenant_id = attrs.get("tenant_id")
            if not tenant_id:
                # If host_id is provided, resolve tenant from host
                host_id = attrs.get("host_id")
                try:
                    host_obj = User.objects.get(id=host_id)
                    tenant = host_obj.tenant
                except User.DoesNotExist:
                    raise serializers.ValidationError({"host_id": "Specified host user does not exist."})
            else:
                try:
                    tenant = Tenant.objects.get(id=tenant_id, is_active=True)
                except Tenant.DoesNotExist:
                    raise serializers.ValidationError({"tenant_id": "Specified tenant does not exist or is inactive."})
        else:
            if not user or not user.tenant:
                raise serializers.ValidationError("Authenticated user must be assigned to an active tenant.")
            tenant = user.tenant

        # Validate host exists and belongs strictly to the target tenant
        host_id = attrs.get("host_id")
        try:
            host_user = User.objects.get(id=host_id, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError({"host_id": "Host user does not exist or is inactive."})

        if host_user.tenant != tenant:
            raise serializers.ValidationError(
                {"host_id": "Host user must belong to the same tenant as the visitor pass request."}
            )

        # Validate validity window
        valid_from = attrs.get("valid_from")
        valid_until = attrs.get("valid_until")
        if valid_from and valid_until and valid_until <= valid_from:
            raise serializers.ValidationError(
                {"valid_until": "Validity end time must be strictly after start time."}
            )

        attrs["tenant"] = tenant
        attrs["host"] = host_user
        # Remove write_only helpers
        attrs.pop("host_id", None)
        attrs.pop("tenant_id", None)
        return attrs


class VisitorPassListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing visitor passes."""

    host_name = serializers.CharField(source="host.get_full_name", read_only=True)
    host_email = serializers.EmailField(source="host.email", read_only=True)

    class Meta:
        model = VisitorPass
        fields = [
            "id",
            "visitor_name",
            "visitor_email",
            "visitor_phone",
            "purpose",
            "status",
            "valid_from",
            "valid_until",
            "host_name",
            "host_email",
            "checked_in_at",
            "checked_out_at",
            "created_at",
        ]


class VisitorPassDetailSerializer(serializers.ModelSerializer):
    """Full detailed serializer for visitor pass details and audit information."""

    host = HostBriefSerializer(read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    approved_by_email = serializers.EmailField(source="approved_by.email", read_only=True)
    rejected_by_email = serializers.EmailField(source="rejected_by.email", read_only=True)
    cancelled_by_email = serializers.EmailField(source="cancelled_by.email", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = VisitorPass
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "host",
            "visitor_name",
            "visitor_email",
            "visitor_phone",
            "purpose",
            "visit_date",
            "valid_from",
            "valid_until",
            "status",
            "qr_token",
            "created_by",
            "created_by_email",
            "approved_by",
            "approved_by_email",
            "approved_at",
            "rejected_by",
            "rejected_by_email",
            "rejected_at",
            "rejection_reason",
            "cancelled_by",
            "cancelled_by_email",
            "cancelled_at",
            "cancellation_reason",
            "checked_in_at",
            "checked_out_at",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PassApprovalActionSerializer(serializers.Serializer):
    """Serializer for approving a pass."""

    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PassRejectionActionSerializer(serializers.Serializer):
    """Serializer for rejecting a pass."""

    reason = serializers.CharField(required=True, min_length=3, help_text="Reason for pass rejection.")


class PassCancellationActionSerializer(serializers.Serializer):
    """Serializer for cancelling a pass."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")


class QRVerificationRequestSerializer(serializers.Serializer):
    """Serializer for gate QR pass verification request."""

    qr_token = serializers.CharField(
        required=True,
        max_length=128,
        help_text="Opaque QR token string presented by the visitor.",
    )
    checkpoint_name = serializers.CharField(
        required=False,
        max_length=100,
        default="",
        help_text="Security gate or checkpoint name (e.g. Main Gate, Lobby B).",
    )


class QRVerificationResponseSerializer(serializers.Serializer):
    """Safe response format returned by QR code verification."""

    valid = serializers.BooleanField()
    status = serializers.CharField()
    pass_id = serializers.UUIDField(required=False, allow_null=True)
    visitor_name = serializers.CharField(required=False, allow_blank=True)
    visitor_phone = serializers.CharField(required=False, allow_blank=True)
    purpose = serializers.CharField(required=False, allow_blank=True)
    host_name = serializers.CharField(required=False, allow_blank=True)
    host_email = serializers.CharField(required=False, allow_blank=True)
    valid_from = serializers.DateTimeField(required=False, allow_null=True)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    can_check_in = serializers.BooleanField()
    can_check_out = serializers.BooleanField()
    message = serializers.CharField()


class CheckInActionSerializer(serializers.Serializer):
    """Serializer for checking in a visitor."""

    qr_token = serializers.CharField(required=False, allow_blank=True, default="")
    pass_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    checkpoint_name = serializers.CharField(required=False, max_length=100, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs.get("qr_token") and not attrs.get("pass_id"):
            raise serializers.ValidationError("Either 'qr_token' or 'pass_id' must be provided.")
        return attrs


class CheckOutActionSerializer(serializers.Serializer):
    """Serializer for checking out a visitor."""

    qr_token = serializers.CharField(required=False, allow_blank=True, default="")
    pass_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    checkpoint_name = serializers.CharField(required=False, max_length=100, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs.get("qr_token") and not attrs.get("pass_id"):
            raise serializers.ValidationError("Either 'qr_token' or 'pass_id' must be provided.")
        return attrs


class VisitorLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for append-only visitor audit logs."""

    visitor_name = serializers.CharField(source="visitor_pass.visitor_name", read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    scanned_by_email = serializers.EmailField(source="scanned_by.email", read_only=True)
    scanned_by_name = serializers.CharField(source="scanned_by.get_full_name", read_only=True)

    class Meta:
        model = VisitorLog
        fields = [
            "id",
            "tenant",
            "visitor_pass",
            "visitor_name",
            "action",
            "action_display",
            "scanned_by",
            "scanned_by_name",
            "scanned_by_email",
            "checkpoint_name",
            "notes",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
