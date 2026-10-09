from django.db import models
from django.conf import settings
from apps.tenants.models import TenantScopedModel

class BlueprintMetadata(TenantScopedModel):
    """
    Blueprint metadata entity.
    Stores metadata, versions, and private object storage paths for floor blueprints.
    Large CAD/SVG/PNG files are stored in private object storage (Amazon S3),
    never as database binary blobs.
    """

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    file_key = models.CharField(
        max_length=512,
        unique=True,
        db_index=True,
        help_text="Object storage key (e.g. blueprints/{tenant_id}/{year}/{month}/{uuid}_{filename})",
    )
    original_filename = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, default="image/png")
    version = models.PositiveIntegerField(default=1, db_index=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_blueprints",
    )
    floor_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Associated floor UUID (linked to Pradeesh's campus module)",
    )

    class Meta:
        verbose_name = "Blueprint Metadata"
        verbose_name_plural = "Blueprint Metadata"
        ordering = ["-version", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "title", "version"]),
        ]

    def __str__(self):
        return f"{self.title} (v{self.version}) [{self.tenant.name}]"
