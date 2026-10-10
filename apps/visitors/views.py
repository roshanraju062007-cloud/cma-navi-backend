from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from apps.authentication.models import UserRole
from apps.tenants.permissions import IsTenantMember
from .models import VisitorPass, VisitorLog, PassStatus, LogAction
from .permissions import (
    CanAccessVisitorPass,
    CanApproveOrRejectPass,
    IsSecurityOrAdmin,
)
from .serializers import (
    VisitorPassCreateSerializer,
    VisitorPassListSerializer,
    VisitorPassDetailSerializer,
    PassApprovalActionSerializer,
    PassRejectionActionSerializer,
    PassCancellationActionSerializer,
    QRVerificationRequestSerializer,
    QRVerificationResponseSerializer,
    CheckInActionSerializer,
    CheckOutActionSerializer,
    VisitorLogSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List visitor passes (scoped to caller permissions)"),
    create=extend_schema(summary="Request a new visitor pass"),
    retrieve=extend_schema(summary="Retrieve visitor pass details and audit history"),
)
class VisitorPassViewSet(viewsets.ModelViewSet):
    """
    Endpoints for managing visitor passes.
    Supports request creation, role-based listing, approval, rejection, and cancellation.
    Arbitrary updates and deletes are disabled to maintain audit integrity.
    """

    search_fields = ["visitor_name", "visitor_email", "visitor_phone", "purpose"]
    ordering_fields = ["created_at", "valid_from", "valid_until", "status"]

    def get_serializer_class(self):
        if self.action == "create":
            return VisitorPassCreateSerializer
        if self.action == "list":
            return VisitorPassListSerializer
        if self.action == "approve":
            return PassApprovalActionSerializer
        if self.action == "reject":
            return PassRejectionActionSerializer
        if self.action == "cancel":
            return PassCancellationActionSerializer
        return VisitorPassDetailSerializer

    def get_permissions(self):
        if self.action in ["approve", "reject"]:
            permission_classes = [IsAuthenticated, CanApproveOrRejectPass]
        elif self.action in ["retrieve", "cancel", "history"]:
            permission_classes = [IsAuthenticated, CanAccessVisitorPass]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return VisitorPass.objects.none()

        # Tenant-level filtering base queryset
        qs = VisitorPass.objects.for_user(user).select_related(
            "tenant", "host", "created_by", "approved_by", "rejected_by", "cancelled_by"
        )

        # Role-based visibility scoping
        if getattr(user, "is_super_admin", False) or user.is_superuser:
            # Super admin can see all passes across tenants
            tenant_id = self.request.query_params.get("tenant_id")
            if tenant_id:
                qs = qs.filter(tenant_id=tenant_id)
        elif getattr(user, "is_tenant_admin", False) or getattr(user, "is_security", False):
            # Tenant admins and Security can view all passes within their tenant
            pass
        elif getattr(user, "is_staff_member", False):
            # When listing, staff can only see passes they host or created.
            # On detail actions, queryset contains tenant passes and object-permissions enforce RBAC with 403 Forbidden.
            if self.action == "list":
                qs = qs.filter(models_Q_or_host(user))
        else:
            # General users only see passes they requested or are host of
            if self.action == "list":
                qs = qs.filter(models_Q_or_host(user))

        # Query filters
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.lower())

        host_id = self.request.query_params.get("host_id")
        if host_id:
            qs = qs.filter(host_id=host_id)

        date_param = self.request.query_params.get("date")
        if date_param:
            qs = qs.filter(visit_date=date_param)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        with transaction.atomic():
            visitor_pass = serializer.save(created_by=user)
            # Record append-only creation audit log
            VisitorLog.objects.create(
                tenant=visitor_pass.tenant,
                visitor_pass=visitor_pass,
                action=LogAction.REQUESTED,
                scanned_by=user,
                checkpoint_name="Visitor Portal",
                notes=f"Pass requested for {visitor_pass.visitor_name} with host {visitor_pass.host.get_full_name() or visitor_pass.host.email}.",
            )

    def update(self, request, *args, **kwargs):
        return Response(
            {"success": False, "error": {"code": "not_allowed", "message": "Direct update is not supported. Use approval, rejection, or cancellation actions."}},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {"success": False, "error": {"code": "not_allowed", "message": "Direct update is not supported. Use approval, rejection, or cancellation actions."}},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"success": False, "error": {"code": "not_allowed", "message": "Visitor pass records cannot be deleted. Use cancellation instead."}},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @extend_schema(
        summary="Approve a visitor pass request",
        request=PassApprovalActionSerializer,
        responses={200: VisitorPassDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        visitor_pass = self.get_object()
        serializer = PassApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("notes", "")

        with transaction.atomic():
            # Concurrently lock the record
            locked_pass = VisitorPass.objects.select_for_update().get(pk=visitor_pass.pk)
            try:
                locked_pass.approve(user=request.user)
            except ValidationError as e:
                return Response(
                    {"success": False, "error": {"code": "invalid_transition", "message": str(e.message if hasattr(e, 'message') else e)}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            VisitorLog.objects.create(
                tenant=locked_pass.tenant,
                visitor_pass=locked_pass,
                action=LogAction.APPROVED,
                scanned_by=request.user,
                checkpoint_name="Approval System",
                notes=notes or f"Approved by {request.user.get_full_name() or request.user.email}.",
            )

        detail_serializer = VisitorPassDetailSerializer(locked_pass)
        return Response({"success": True, "pass": detail_serializer.data})

    @extend_schema(
        summary="Reject a visitor pass request",
        request=PassRejectionActionSerializer,
        responses={200: VisitorPassDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        visitor_pass = self.get_object()
        serializer = PassRejectionActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]

        with transaction.atomic():
            locked_pass = VisitorPass.objects.select_for_update().get(pk=visitor_pass.pk)
            try:
                locked_pass.reject(user=request.user, reason=reason)
            except ValidationError as e:
                return Response(
                    {"success": False, "error": {"code": "invalid_transition", "message": str(e.message if hasattr(e, 'message') else e)}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            VisitorLog.objects.create(
                tenant=locked_pass.tenant,
                visitor_pass=locked_pass,
                action=LogAction.REJECTED,
                scanned_by=request.user,
                checkpoint_name="Approval System",
                notes=f"Rejected: {reason}",
            )

        detail_serializer = VisitorPassDetailSerializer(locked_pass)
        return Response({"success": True, "pass": detail_serializer.data})

    @extend_schema(
        summary="Cancel an eligible visitor pass request",
        request=PassCancellationActionSerializer,
        responses={200: VisitorPassDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        visitor_pass = self.get_object()
        serializer = PassCancellationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        with transaction.atomic():
            locked_pass = VisitorPass.objects.select_for_update().get(pk=visitor_pass.pk)
            try:
                locked_pass.cancel(user=request.user, reason=reason)
            except ValidationError as e:
                return Response(
                    {"success": False, "error": {"code": "invalid_transition", "message": str(e.message if hasattr(e, 'message') else e)}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            VisitorLog.objects.create(
                tenant=locked_pass.tenant,
                visitor_pass=locked_pass,
                action=LogAction.CANCELLED,
                scanned_by=request.user,
                checkpoint_name="Portal/Management",
                notes=reason or f"Cancelled by {request.user.get_full_name() or request.user.email}.",
            )

        detail_serializer = VisitorPassDetailSerializer(locked_pass)
        return Response({"success": True, "pass": detail_serializer.data})

    @extend_schema(
        summary="View audit history for a visitor pass",
        responses={200: VisitorLogSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        visitor_pass = self.get_object()
        logs = visitor_pass.logs.all().order_by("-created_at")
        serializer = VisitorLogSerializer(logs, many=True)
        return Response({"success": True, "results": serializer.data})


def models_Q_or_host(user):
    from django.db.models import Q
    return Q(host=user) | Q(created_by=user)


@extend_schema(
    summary="Validate QR pass at security gate or checkpoint",
    request=QRVerificationRequestSerializer,
    responses={200: QRVerificationResponseSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSecurityOrAdmin])
def verify_qr_view(request):
    """
    Gate QR verification endpoint.
    Verifies pass validity window, status, and tenant isolation.
    Does NOT leak information regarding whether another tenant's pass exists.
    """
    serializer = QRVerificationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    qr_token = serializer.validated_data["qr_token"].strip()
    checkpoint_name = serializer.validated_data.get("checkpoint_name", "Security Checkpoint")
    user = request.user

    # Attempt to locate pass matching the QR token
    try:
        visitor_pass = VisitorPass.objects.get(qr_token=qr_token)
    except VisitorPass.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": {
                    "code": "invalid_qr",
                    "status_code": 404,
                    "message": "Unrecognized or invalid visitor pass QR code.",
                },
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # CRITICAL: Strict cross-tenant isolation defense
    # If the pass belongs to a different tenant and caller is not super_admin,
    # return generic 404 so caller cannot deduce the pass exists elsewhere.
    if not (getattr(user, "is_super_admin", False) or user.is_superuser):
        if visitor_pass.tenant != user.tenant:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "invalid_qr",
                        "status_code": 404,
                        "message": "Unrecognized or invalid visitor pass QR code.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    now = timezone.now()
    valid = False
    can_check_in = False
    can_check_out = False
    message = ""

    # Check status and validity window
    if visitor_pass.status == PassStatus.PENDING:
        message = "Pass is currently pending host approval and cannot be used for entry."
    elif visitor_pass.status == PassStatus.REJECTED:
        message = f"Pass was rejected: {visitor_pass.rejection_reason or 'No reason provided.'}"
    elif visitor_pass.status == PassStatus.CANCELLED:
        message = "Pass was cancelled."
    elif visitor_pass.status == PassStatus.CHECKED_OUT:
        message = "Pass has already been checked out and completed."
    elif visitor_pass.status == PassStatus.EXPIRED or now > visitor_pass.valid_until:
        if visitor_pass.status != PassStatus.EXPIRED:
            visitor_pass.status = PassStatus.EXPIRED
            visitor_pass.save(update_fields=["status", "updated_at"])
        message = "Pass validity has expired."
    elif now < visitor_pass.valid_from:
        message = f"Pass is not yet active. Valid from {visitor_pass.valid_from.isoformat()}."
    elif visitor_pass.status == PassStatus.CHECKED_IN:
        valid = True
        can_check_out = True
        message = "Visitor is currently checked in. Eligible for check-out."
    elif visitor_pass.status == PassStatus.APPROVED:
        valid = True
        can_check_in = True
        message = "Pass is valid and approved for entry check-in."
    else:
        message = f"Pass is not valid for entry (status: {visitor_pass.status})."

    # Audit the QR verification scan
    VisitorLog.objects.create(
        tenant=visitor_pass.tenant,
        visitor_pass=visitor_pass,
        action=LogAction.QR_VERIFIED,
        scanned_by=user,
        checkpoint_name=checkpoint_name,
        notes=f"QR verified at {checkpoint_name}. Result: {message}",
        metadata={"valid": valid, "status": visitor_pass.status},
    )

    host_name = visitor_pass.host.get_full_name() or visitor_pass.host.email
    return Response(
        {
            "success": True,
            "verification": {
                "valid": valid,
                "status": visitor_pass.status,
                "pass_id": str(visitor_pass.id),
                "visitor_name": visitor_pass.visitor_name,
                "visitor_phone": visitor_pass.visitor_phone,
                "purpose": visitor_pass.purpose,
                "host_name": host_name,
                "host_email": visitor_pass.host.email,
                "valid_from": visitor_pass.valid_from,
                "valid_until": visitor_pass.valid_until,
                "can_check_in": can_check_in,
                "can_check_out": can_check_out,
                "message": message,
            },
        }
    )


@extend_schema(
    summary="Record visitor gate check-in",
    request=CheckInActionSerializer,
    responses={200: VisitorPassDetailSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSecurityOrAdmin])
def check_in_view(request):
    """
    Gate check-in endpoint.
    Performs atomic lock to prevent concurrent duplicate entries.
    """
    serializer = CheckInActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    qr_token = serializer.validated_data.get("qr_token", "").strip()
    pass_id = serializer.validated_data.get("pass_id")
    checkpoint_name = serializer.validated_data.get("checkpoint_name", "Security Gate")
    notes = serializer.validated_data.get("notes", "")
    user = request.user

    with transaction.atomic():
        try:
            if qr_token:
                locked_pass = VisitorPass.objects.select_for_update().get(qr_token=qr_token)
            else:
                locked_pass = VisitorPass.objects.select_for_update().get(id=pass_id)
        except VisitorPass.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "not_found",
                        "status_code": 404,
                        "message": "Visitor pass not found.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Cross-tenant isolation check
        if not (getattr(user, "is_super_admin", False) or user.is_superuser):
            if locked_pass.tenant != user.tenant:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "not_found",
                            "status_code": 404,
                            "message": "Visitor pass not found.",
                        },
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            locked_pass.check_in(user=user)
        except ValidationError as e:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "check_in_failed",
                        "message": str(e.message if hasattr(e, "message") else e),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        VisitorLog.objects.create(
            tenant=locked_pass.tenant,
            visitor_pass=locked_pass,
            action=LogAction.CHECK_IN,
            scanned_by=user,
            checkpoint_name=checkpoint_name,
            notes=notes or f"Checked in at {checkpoint_name} by {user.get_full_name() or user.email}.",
        )

    detail_serializer = VisitorPassDetailSerializer(locked_pass)
    return Response(
        {
            "success": True,
            "message": f"Visitor {locked_pass.visitor_name} checked in successfully.",
            "pass": detail_serializer.data,
        }
    )


@extend_schema(
    summary="Record visitor gate check-out",
    request=CheckOutActionSerializer,
    responses={200: VisitorPassDetailSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSecurityOrAdmin])
def check_out_view(request):
    """
    Gate check-out endpoint.
    Performs atomic lock to prevent concurrent duplicate exits.
    """
    serializer = CheckOutActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    qr_token = serializer.validated_data.get("qr_token", "").strip()
    pass_id = serializer.validated_data.get("pass_id")
    checkpoint_name = serializer.validated_data.get("checkpoint_name", "Security Gate")
    notes = serializer.validated_data.get("notes", "")
    user = request.user

    with transaction.atomic():
        try:
            if qr_token:
                locked_pass = VisitorPass.objects.select_for_update().get(qr_token=qr_token)
            else:
                locked_pass = VisitorPass.objects.select_for_update().get(id=pass_id)
        except VisitorPass.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "not_found",
                        "status_code": 404,
                        "message": "Visitor pass not found.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Cross-tenant isolation check
        if not (getattr(user, "is_super_admin", False) or user.is_superuser):
            if locked_pass.tenant != user.tenant:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "not_found",
                            "status_code": 404,
                            "message": "Visitor pass not found.",
                        },
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            locked_pass.check_out(user=user)
        except ValidationError as e:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "check_out_failed",
                        "message": str(e.message if hasattr(e, "message") else e),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        VisitorLog.objects.create(
            tenant=locked_pass.tenant,
            visitor_pass=locked_pass,
            action=LogAction.CHECK_OUT,
            scanned_by=user,
            checkpoint_name=checkpoint_name,
            notes=notes or f"Checked out at {checkpoint_name} by {user.get_full_name() or user.email}.",
        )

    detail_serializer = VisitorPassDetailSerializer(locked_pass)
    return Response(
        {
            "success": True,
            "message": f"Visitor {locked_pass.visitor_name} checked out successfully.",
            "pass": detail_serializer.data,
        }
    )


@extend_schema_view(
    list=extend_schema(summary="List visitor audit logs (read-only)"),
    retrieve=extend_schema(summary="Retrieve visitor audit log entry"),
)
class VisitorLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for visitor logs and audit trails.
    Strictly forbids modifications or deletions.
    """

    serializer_class = VisitorLogSerializer
    permission_classes = [IsAuthenticated, IsSecurityOrAdmin]
    ordering_fields = ["created_at", "action"]

    def get_queryset(self):
        user = self.request.user
        qs = VisitorLog.objects.for_user(user).select_related("visitor_pass", "scanned_by", "tenant")

        pass_id = self.request.query_params.get("pass_id")
        if pass_id:
            qs = qs.filter(visitor_pass_id=pass_id)

        action_param = self.request.query_params.get("action")
        if action_param:
            qs = qs.filter(action=action_param)

        return qs
