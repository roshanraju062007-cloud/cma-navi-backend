import os
import uuid
from datetime import datetime
from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
import logging

logger = logging.getLogger(__name__)

class BlueprintStorageService:
    """
    Service for managing secure private object storage for blueprints (CAD, SVG, PNG).
    Supports AWS S3 presigned URLs for direct client uploads/downloads,
    with local signed URLs fallback for development environments.
    """

    def __init__(self):
        self.use_s3 = getattr(settings, "USE_S3_STORAGE", False)
        self.bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "wayora-blueprints")
        self.region_name = getattr(settings, "AWS_S3_REGION_NAME", "us-east-1")
        self.expiry = getattr(settings, "AWS_PRESIGNED_EXPIRY_SECONDS", 3600)
        self._s3_client = None

    @property
    def s3_client(self):
        if self._s3_client is None and self.use_s3:
            import boto3
            from botocore.config import Config

            self._s3_client = boto3.client(
                "s3",
                region_name=self.region_name,
                aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
                aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
                config=Config(signature_version="s3v4"),
            )
        return self._s3_client

    def generate_storage_key(self, tenant_id: str, file_name: str) -> str:
        """
        Generates a partitioned, collision-free private object key.
        Format: blueprints/{tenant_id}/{year}/{month}/{unique_id}_{clean_filename}
        """
        now = datetime.utcnow()
        clean_name = os.path.basename(file_name).replace(" ", "_")
        unique_prefix = uuid.uuid4().hex[:12]
        return f"blueprints/{tenant_id}/{now.year}/{now.month:02d}/{unique_prefix}_{clean_name}"

    def generate_presigned_upload_url(
        self, tenant_id: str, file_name: str, content_type: str = "image/png"
    ) -> dict:
        """
        Generate a presigned PUT URL allowing the frontend to upload
        large blueprint files directly to private object storage.
        """
        object_key = self.generate_storage_key(tenant_id, file_name)

        if self.use_s3 and self.s3_client:
            try:
                presigned_url = self.s3_client.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": object_key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=self.expiry,
                )
                return {
                    "storage_provider": "s3",
                    "file_key": object_key,
                    "upload_url": presigned_url,
                    "expires_in_seconds": self.expiry,
                    "http_method": "PUT",
                    "headers": {"Content-Type": content_type},
                }
            except Exception as exc:
                logger.error("Failed to generate S3 presigned upload URL: %s", exc)
                raise

        # Fallback to local signed URL for development
        signer = TimestampSigner()
        signed_token = signer.sign(f"{tenant_id}:{object_key}")
        return {
            "storage_provider": "local_private",
            "file_key": object_key,
            "upload_url": f"/api/v1/blueprints/storage/upload/?token={signed_token}",
            "expires_in_seconds": self.expiry,
            "http_method": "POST",
            "headers": {"Content-Type": content_type},
        }

    def generate_presigned_download_url(self, object_key: str) -> dict:
        """
        Generate a temporary, time-limited presigned GET URL
        to view or download a private blueprint file.
        """
        if self.use_s3 and self.s3_client:
            try:
                presigned_url = self.s3_client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": self.bucket_name, "Key": object_key},
                    ExpiresIn=self.expiry,
                )
                return {
                    "storage_provider": "s3",
                    "download_url": presigned_url,
                    "expires_in_seconds": self.expiry,
                }
            except Exception as exc:
                logger.error("Failed to generate S3 presigned download URL: %s", exc)
                raise

        # Fallback to local signed URL
        signer = TimestampSigner()
        signed_token = signer.sign(object_key)
        return {
            "storage_provider": "local_private",
            "download_url": f"/api/v1/blueprints/storage/download/?token={signed_token}",
            "expires_in_seconds": self.expiry,
        }

storage_service = BlueprintStorageService()
