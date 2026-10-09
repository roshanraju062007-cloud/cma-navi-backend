from django.contrib import admin
from .models import BlueprintMetadata

@admin.register(BlueprintMetadata)
class BlueprintMetadataAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "tenant",
        "version",
        "mime_type",
        "file_size_bytes",
        "is_active",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("tenant", "mime_type", "version", "is_active")
    search_fields = ("title", "file_key", "original_filename")
