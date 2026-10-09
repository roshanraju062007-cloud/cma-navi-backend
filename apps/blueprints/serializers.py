from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.common.storage import storage_service
from .models import BlueprintMetadata

class BlueprintMetadataSerializer(serializers.ModelSerializer):
    """Serializer for blueprint metadata with presigned access URL."""

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

    @extend_schema_field(serializers.DictField)
    def get_download_url(self, obj):
        try:
            return storage_service.generate_presigned_download_url(obj.file_key)
        except Exception:
            return None


class BlueprintUploadRequestSerializer(serializers.Serializer):
    """Serializer for requesting a presigned upload URL."""

    filename = serializers.CharField(max_length=255, required=True)
    content_type = serializers.CharField(max_length=100, default="image/png")
    title = serializers.CharField(max_length=255, required=True)
    version = serializers.IntegerField(default=1, min_value=1)
