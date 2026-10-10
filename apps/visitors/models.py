import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from apps.tenants.models import TenantScopedModel


class PassStatus(models.TextChoices):
    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CHECKED_IN = "checked_in", "Checked In"
    CHECKED_OUT = "checked_out", "Checked Out"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class LogAction(models.TextChoices):
    REQUESTED = "requested", "Pass Requested"
    APPROVED = "approved", "Pass Approved"
    REJECTED = "rejected", "Pass Rejected"
    QR_VERIFIED = "qr_verified", "QR Verified"
    CHECK_IN = "check_in", "Check In"
    CHECK_OUT = "check_out", "Check Out"
    CANCELLED = "cancelled", "Pass Cancelled"
    EXPIRED = "expired", "Pass Expired"


def generate_secure_qr_token():
    """Generates an unpredictable, cryptographically random QR token without embedding PII."""
    return secrets.token_hex(32)


class VisitorPass(TenantScopedModel):
    """
    Visitor pass entity for multi-tenant indoor navigation and access management.
    Inherits UUID pk, created_at, updated_at, is_active from BaseModel,
    and tenant scoping from TenantScopedModel.
    """

    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_passes",
        help_text="Staff or faculty host member",
        db_index=True,
    )
    visitor_name = models.CharField(max_length=255)
    visitor_email = models.EmailField()
    visitor_phone = models.CharField(max_length=30)
    purpose = models.CharField(max_length=255)
    visit_date = models.DateField(null=True, blank=True)
    valid_from = models.DateTimeField(db_index=True)
    valid_until = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=30,
        choices=PassStatus.choices,
        default=PassStatus.PENDING,
        db_index=True,
    )
    qr_token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        default=generate_secure_qr_token,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_passes",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_passes",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_passes",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_passes",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Visitor Pass"
        verbose_name_plural = "Visitor Passes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "valid_from", "valid_until"]),
            models.Index(fields=["host", "status"]),
            models.Index(fields=["qr_token"]),
        ]

    def __str__(self):
        return f"Pass {self.id} for {self.visitor_name} ({self.status})"

    def clean(self):
        super().clean()
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": "Validity end time must be after start time."})

    def save(self, *args, **kwargs):
        if not self.visit_date and self.valid_from:
            self.visit_date = self.valid_from.date()
        self.clean()
        super().save(*args, **kwargs)

    def is_currently_valid(self):
        """Checks if current time falls within valid_from and valid_until."""
        now = timezone.now()
        return self.valid_from <= now <= self.valid_until

    def is_expired(self):
        """Checks if pass validity window has lapsed."""
        return timezone.now() > self.valid_until

    def approve(self, user):
        """Approve a pending pass request."""
        if self.status != PassStatus.PENDING:
            raise ValidationError(
                f"Cannot approve pass with status '{self.status}'. Only pending passes can be approved."
            )
        now = timezone.now()
        if now > self.valid_until:
            self.status = PassStatus.EXPIRED
            self.save(update_fields=["status", "updated_at"])
            raise ValidationError("Cannot approve an expired pass.")

        self.status = PassStatus.APPROVED
        self.approved_by = user
        self.approved_at = now
        self.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

    def reject(self, user, reason=""):
        """Reject a pending pass request."""
        if self.status != PassStatus.PENDING:
            raise ValidationError(
                f"Cannot reject pass with status '{self.status}'. Only pending passes can be rejected."
            )
        self.status = PassStatus.REJECTED
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save(
            update_fields=[
                "status",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
                "updated_at",
            ]
        )

    def cancel(self, user, reason=""):
        """Cancel a pending or approved pass."""
        if self.status not in [PassStatus.PENDING, PassStatus.APPROVED]:
            raise ValidationError(
                f"Cannot cancel pass with status '{self.status}'. Only pending or approved passes can be cancelled."
            )
        self.status = PassStatus.CANCELLED
        self.cancelled_by = user
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save(
            update_fields=[
                "status",
                "cancelled_by",
                "cancelled_at",
                "cancellation_reason",
                "updated_at",
            ]
        )

    def check_in(self, user):
        """Check in an approved visitor."""
        now = timezone.now()
        if self.status == PassStatus.CHECKED_IN:
            raise ValidationError("Pass has already been checked in.")
        if self.status == PassStatus.CHECKED_OUT:
            raise ValidationError("Pass has already been checked out and cannot be reused.")
        if self.status == PassStatus.REJECTED:
            raise ValidationError("Cannot check in a rejected pass.")
        if self.status == PassStatus.CANCELLED:
            raise ValidationError("Cannot check in a cancelled pass.")
        if self.status == PassStatus.PENDING:
            raise ValidationError("Pass is pending approval and cannot be used for entry.")
        if self.status == PassStatus.EXPIRED or now > self.valid_until:
            if self.status != PassStatus.EXPIRED:
                self.status = PassStatus.EXPIRED
                self.save(update_fields=["status", "updated_at"])
            raise ValidationError("Pass validity has expired.")
        if self.status != PassStatus.APPROVED:
            raise ValidationError(f"Cannot check in pass with status '{self.status}'.")

        if now < self.valid_from:
            raise ValidationError("Pass is not yet active. Entry is not permitted before valid_from.")

        self.status = PassStatus.CHECKED_IN
        self.checked_in_at = now
        self.save(update_fields=["status", "checked_in_at", "updated_at"])

    def check_out(self, user):
        """Check out an active visitor."""
        if self.status != PassStatus.CHECKED_IN:
            raise ValidationError(
                f"Cannot check out a visitor whose pass status is '{self.status}'. Only checked-in passes can be checked out."
            )
        now = timezone.now()
        self.status = PassStatus.CHECKED_OUT
        self.checked_out_at = now
        self.save(update_fields=["status", "checked_out_at", "updated_at"])


class VisitorLog(TenantScopedModel):
    """
    Append-only audit trail and visit history record for visitor passes.
    Tracks requests, approvals, rejections, QR scans, check-ins, check-outs, and cancellations.
    Once created, entries are immutable and cannot be updated or deleted.
    """

    visitor_pass = models.ForeignKey(
        VisitorPass,
        on_delete=models.CASCADE,
        related_name="logs",
        db_index=True,
    )
    action = models.CharField(
        max_length=30,
        choices=LogAction.choices,
        db_index=True,
    )
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scanned_visitor_logs",
        help_text="Acting user (security, host, admin)",
    )
    checkpoint_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. Gate 1, Tower B Lobby",
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Visitor Log"
        verbose_name_plural = "Visitor Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "action"]),
            models.Index(fields=["visitor_pass", "action"]),
            models.Index(fields=["scanned_by", "created_at"]),
        ]

    def __str__(self):
        return f"Log {self.action} on Pass {self.visitor_pass_id} at {self.created_at}"

    def save(self, *args, **kwargs):
        # Enforce append-only immutability
        if self.pk and not self._state.adding:
            # Check if this object already exists in the database
            if VisitorLog.objects.filter(pk=self.pk).exists():
                raise ValidationError("Visitor log entries are immutable and append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Visitor log entries are permanent audit records and cannot be deleted.")
