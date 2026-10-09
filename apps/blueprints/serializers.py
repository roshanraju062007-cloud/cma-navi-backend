import os
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.common.storage import storage_service
from .models import BlueprintMetadata

ALLOWED_CONTENT_TYPES = [
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "application/pdf",
    "image/webp",
]
ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".svg", ".pdf", ".webp", ".dwg"]
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB (configurable ceiling)

class BlueprintMetadataSerializer(serializers.ModelSerializer):
    """Serializer for blueprint metadata with presigned access URL and security checks."""

    download_url = serializers.SerializerMethodField()
    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email", read_only=True, default=None
    )

    class Meta:
        model = BlueprintMetadata
        fields = [
            "id",
            "tenant",
            "title",
            "description",
            "file_key",
            "original_filename",
            "file_size_bytes",
            "mime_type",
            "version",
            "checksum_sha256",
            "uploaded_by",
            "uploaded_by_email",
            "download_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "uploaded_by",
            "download_url",
            "created_at",
            "updated_at",
        ]

    def validate_file_size_bytes(self, value):
        if value < 0:
            raise serializers.ValidationError("File size cannot be negative.")
        if value > MAX_FILE_SIZE_BYTES:
            raise serializers.ValidationError(
                f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            )
        return value

    def validate_mime_type(self, value):
        if value.lower() not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"MIME type '{value}' is not supported. Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}."
            )
        return value.lower()

    def validate_file_key(self, value):
        if ".." in value or "\\" in value:
            raise serializers.ValidationError("Invalid file key: path traversal sequence detected.")

        request = self.context.get("request")
        if request and request.user and not request.user.is_super_admin:
            expected_prefix = f"blueprints/{request.user.tenant_id}/"
            if not value.startswith(expected_prefix):
                raise serializers.ValidationError(
                    "Security violation: Object key must reside within your assigned tenant partition."
                )
        return value

    @extend_schema_field(serializers.DictField)
    def get_download_url(self, obj):
        try:
            return storage_service.generate_presigned_download_url(obj.file_key)
        except Exception:
            return None


class BlueprintUploadRequestSerializer(serializers.Serializer):
    """Serializer for requesting a presigned upload URL with strict validation."""

    filename = serializers.CharField(max_length=255, required=True)
    content_type = serializers.CharField(max_length=100, default="image/png")
    title = serializers.CharField(max_length=255, required=True)
    version = serializers.IntegerField(default=1, min_value=1)

    def validate_filename(self, value):
        clean_name = os.path.basename(value)
        if ".." in value or "/" in value or "\\" in value:
            raise serializers.ValidationError("Filename contains invalid path characters.")
        ext = os.path.splitext(clean_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"File extension '{ext}' is not permitted for blueprints. Allowed: {', '.join(ALLOWED_EXTENSIONS)}."
            )
        return clean_name

    def validate_content_type(self, value):
        val = value.lower().strip()
        if val not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"Content type '{val}' is not allowed. Supported: {', '.join(ALLOWED_CONTENT_TYPES)}."
            )
        return val
