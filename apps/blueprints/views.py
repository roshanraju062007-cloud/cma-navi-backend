import os
from django.conf import settings
from django.http import HttpResponse, Http404
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.tenants.permissions import IsTenantMember, IsTenantAdmin
from apps.common.storage import storage_service
from .models import BlueprintMetadata
from .serializers import (
    BlueprintMetadataSerializer,
    BlueprintUploadRequestSerializer,
)

@extend_schema_view(
    list=extend_schema(summary="List blueprints (tenant-scoped)"),
    create=extend_schema(summary="Register blueprint metadata after upload"),
    retrieve=extend_schema(summary="Retrieve blueprint metadata with presigned download URL"),
    update=extend_schema(summary="Update blueprint metadata"),
    partial_update=extend_schema(summary="Partially update blueprint metadata"),
    destroy=extend_schema(summary="Delete/deactivate blueprint metadata"),
)
class BlueprintViewSet(viewsets.ModelViewSet):
    """
    Endpoints for blueprint metadata management and presigned storage access.
    Enforces strict tenant isolation: users only access blueprints for their tenant.
    Creation/Updates require Tenant Admin or Super Admin permissions.
    """

    serializer_class = BlueprintMetadataSerializer
    search_fields = ["title", "original_filename"]
    ordering_fields = ["title", "version", "created_at"]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "request_upload_url"]:
            permission_classes = [IsAuthenticated, IsTenantAdmin]
        else:
            permission_classes = [IsAuthenticated, IsTenantMember]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        qs = BlueprintMetadata.objects.for_user(self.request.user)
        floor_id = self.request.query_params.get("floor_id")
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ("true", "1"))
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        tenant = getattr(user, "tenant", None)
        if user.is_super_admin and "tenant" in self.request.data:
            from apps.tenants.models import Tenant

            tenant = Tenant.objects.get(id=self.request.data["tenant"])
        serializer.save(tenant=tenant, uploaded_by=user)

    @extend_schema(
        summary="Request presigned upload URL for direct blueprint upload",
        request=BlueprintUploadRequestSerializer,
        responses={200: dict},
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsTenantAdmin],
    )
    def request_upload_url(self, request):
        """
        Generates a secure presigned upload URL (e.g. AWS S3 PUT) so large blueprint
        files are uploaded directly to private object storage from the client.
        """
        serializer = BlueprintUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        tenant_id = str(user.tenant.id) if user.tenant else "global"
        filename = serializer.validated_data["filename"]
        content_type = serializer.validated_data.get("content_type", "image/png")

        upload_data = storage_service.generate_presigned_upload_url(
            tenant_id=tenant_id,
            file_name=filename,
            content_type=content_type,
        )

        metadata = {
            "title": serializer.validated_data["title"],
            "version": serializer.validated_data["version"],
        }
        if serializer.validated_data.get("floor_id"):
            metadata["floor_id"] = str(serializer.validated_data["floor_id"])

        return Response(
            {
                "success": True,
                "upload": upload_data,
                "metadata": metadata,
            }
        )

    @extend_schema(
        summary="Get refreshed presigned download URL for a blueprint",
        responses={200: dict},
    )
    @action(detail=True, methods=["get"])
    def download_url(self, request, pk=None):
        """Generates a temporary signed download URL for the blueprint."""
        blueprint = self.get_object()
        download_data = storage_service.generate_presigned_download_url(blueprint.file_key)
        return Response({"success": True, "download": download_data})


@extend_schema(exclude=True)
@api_view(["POST"])
@permission_classes([AllowAny])
def local_storage_upload_view(request):
    """
    Local private object storage upload endpoint for development environments
    when S3 is not active. Validates timestamped signature.
    """
    token = request.query_params.get("token")
    if not token:
        return Response(
            {"success": False, "error": "Missing upload token."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    signer = TimestampSigner()
    try:
        data = signer.unsign(token, max_age=storage_service.expiry)
        tenant_id, object_key = data.split(":", 1)
    except (BadSignature, SignatureExpired, ValueError):
        return Response(
            {"success": False, "error": "Invalid or expired upload token."},
            status=status.HTTP_403_FORBIDDEN,
        )

    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response(
            {"success": False, "error": "No file uploaded in form field 'file'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from pathlib import Path
    media_root = (settings.BASE_DIR / "media").resolve()
    target_path = (media_root / object_key).resolve()

    # Prevent path traversal attacks escaping media_root
    try:
        target_path.relative_to(media_root)
    except ValueError:
        return Response(
            {"success": False, "error": "Access denied: Path traversal detected."},
            status=status.HTTP_403_FORBIDDEN,
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb+") as dest:
        for chunk in file_obj.chunks():
            dest.write(chunk)

    return Response(
        {
            "success": True,
            "message": "File stored successfully in private storage.",
            "file_key": object_key,
        }
    )


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
def local_storage_download_view(request):
    """
    Local private storage download view with signed token verification and path safety.
    """
    token = request.query_params.get("token")
    if not token:
        raise Http404("Missing access token.")

    signer = TimestampSigner()
    try:
        object_key = signer.unsign(token, max_age=storage_service.expiry)
    except (BadSignature, SignatureExpired):
        return Response(
            {"success": False, "error": "Invalid or expired access token."},
            status=status.HTTP_403_FORBIDDEN,
        )

    from pathlib import Path
    media_root = (settings.BASE_DIR / "media").resolve()
    file_path = (media_root / object_key).resolve()

    # Prevent path traversal attacks escaping media_root
    try:
        file_path.relative_to(media_root)
    except ValueError:
        return Response(
            {"success": False, "error": "Access denied: Path traversal detected."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not file_path.exists() or not file_path.is_file():
        raise Http404("Blueprint file not found in storage.")

    with open(file_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/octet-stream")
        response["Content-Disposition"] = f'inline; filename="{os.path.basename(file_path)}"'
        return response
