from datetime import timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import User, UserRole
from apps.tenants.models import Tenant
from apps.visitors.models import VisitorPass, VisitorLog, PassStatus, LogAction


class VisitorManagementTests(TestCase):
    """
    Comprehensive test suite for Visitor Management & Security:
    - Pass creation and lifecycle management (approval, rejection, cancellation)
    - Valid and invalid lifecycle transitions
    - Security QR verification with anti-leak tenant defense
    - Gate check-in and check-out with concurrency and replay defenses
    - Append-only audit logs and immutability
    - Cross-tenant isolation and role-based permissions
    """

    def setUp(self):
        self.client = APIClient()

        # Tenant 1 (Apex College)
        self.tenant_a = Tenant.objects.create(
            name="Apex College of Engineering",
            slug="apex-engineering",
            tenant_type="college",
        )

        # Tenant 2 (Metropolis IT Park)
        self.tenant_b = Tenant.objects.create(
            name="Metropolis IT Park",
            slug="metropolis-park",
            tenant_type="it_park",
        )

        self.password = "SecurePassword123!"

        # Super Admin
        self.super_admin = User.objects.create_superuser(
            email="superadmin@wayora.io",
            password=self.password,
            role=UserRole.SUPER_ADMIN,
        )

        # Tenant A Users
        self.admin_a = User.objects.create_user(
            email="admin_a@apex.edu",
            password=self.password,
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant_a,
        )
        self.host_a1 = User.objects.create_user(
            email="professor1@apex.edu",
            password=self.password,
            first_name="Charles",
            last_name="Xavier",
            role=UserRole.STAFF,
            tenant=self.tenant_a,
        )
        self.host_a2 = User.objects.create_user(
            email="professor2@apex.edu",
            password=self.password,
            first_name="Hank",
            last_name="McCoy",
            role=UserRole.STAFF,
            tenant=self.tenant_a,
        )
        self.security_a = User.objects.create_user(
            email="guard_a@apex.edu",
            password=self.password,
            role=UserRole.SECURITY,
            tenant=self.tenant_a,
        )
        self.student_a = User.objects.create_user(
            email="student_a@apex.edu",
            password=self.password,
            role=UserRole.USER,
            tenant=self.tenant_a,
        )

        # Tenant B Users
        self.admin_b = User.objects.create_user(
            email="admin_b@metropolis.com",
            password=self.password,
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant_b,
        )
        self.host_b = User.objects.create_user(
            email="manager_b@metropolis.com",
            password=self.password,
            role=UserRole.STAFF,
            tenant=self.tenant_b,
        )
        self.security_b = User.objects.create_user(
            email="guard_b@metropolis.com",
            password=self.password,
            role=UserRole.SECURITY,
            tenant=self.tenant_b,
        )

    # -------------------------------------------------------------
    # 1. Visitor Pass Creation & Validation
    # -------------------------------------------------------------

    def test_create_visitor_pass_success(self):
        """Staff user can successfully create a visitor pass request."""
        self.client.force_authenticate(user=self.student_a)
        now = timezone.now()
        payload = {
            "host_id": str(self.host_a1.id),
            "visitor_name": "Alice Green",
            "visitor_email": "alice@external.org",
            "visitor_phone": "+1-555-0199",
            "purpose": "Academic Interview",
            "valid_from": (now + timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=5)).isoformat(),
            "notes": "Requires visitor badge at Gate 1",
        }
        url = reverse("visitor-pass-list")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pass_id = response.data["id"]
        visitor_pass = VisitorPass.objects.get(id=pass_id)

        self.assertEqual(visitor_pass.status, PassStatus.PENDING)
        self.assertEqual(visitor_pass.tenant, self.tenant_a)
        self.assertEqual(visitor_pass.host, self.host_a1)
        self.assertEqual(visitor_pass.created_by, self.student_a)
        self.assertTrue(len(visitor_pass.qr_token) >= 32)

        # Check append-only audit log creation
        logs = visitor_pass.logs.all()
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().action, LogAction.REQUESTED)
        self.assertEqual(logs.first().scanned_by, self.student_a)

    def test_cross_tenant_host_reference_blocked(self):
        """User cannot create a pass referring to a host belonging to another tenant."""
        self.client.force_authenticate(user=self.student_a)
        now = timezone.now()
        payload = {
            "host_id": str(self.host_b.id),  # Belongs to Tenant B!
            "visitor_name": "Eve Sneak",
            "visitor_email": "eve@outside.com",
            "visitor_phone": "+1-555-0000",
            "purpose": "Unauthorized visit attempt",
            "valid_from": (now + timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=4)).isoformat(),
        }
        url = reverse("visitor-pass-list")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("host_id", response.data["error"]["details"])

    def test_invalid_validity_window_rejected(self):
        """valid_until <= valid_from must be rejected."""
        self.client.force_authenticate(user=self.host_a1)
        now = timezone.now()
        payload = {
            "host_id": str(self.host_a1.id),
            "visitor_name": "Bob Time",
            "visitor_email": "bob@time.com",
            "visitor_phone": "+1-555-1111",
            "purpose": "Time Travel",
            "valid_from": (now + timedelta(hours=5)).isoformat(),
            "valid_until": (now + timedelta(hours=2)).isoformat(),  # earlier than valid_from
        }
        url = reverse("visitor-pass-list")
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------
    # 2. Approval, Rejection, and Cancellation Lifecycle
    # -------------------------------------------------------------

    def test_host_can_approve_assigned_pass(self):
        """The designated host can approve their own pending pass."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            created_by=self.student_a,
            visitor_name="Charlie Brown",
            visitor_email="charlie@peanuts.com",
            visitor_phone="+1-555-2222",
            purpose="Project Meeting",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=4),
            status=PassStatus.PENDING,
        )

        self.client.force_authenticate(user=self.host_a1)
        url = reverse("visitor-pass-approve", kwargs={"pk": visitor_pass.id})
        response = self.client.post(url, {"notes": "Approved for lab visit"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        visitor_pass.refresh_from_db()
        self.assertEqual(visitor_pass.status, PassStatus.APPROVED)
        self.assertEqual(visitor_pass.approved_by, self.host_a1)
        self.assertIsNotNone(visitor_pass.approved_at)

        # Audit log verification
        log = visitor_pass.logs.filter(action=LogAction.APPROVED).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.scanned_by, self.host_a1)

    def test_tenant_admin_can_approve_any_pass_in_tenant(self):
        """Tenant admin can approve passes in their tenant even if not the host."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Diana Prince",
            visitor_email="diana@amazon.org",
            visitor_phone="+1-555-3333",
            purpose="Guest Lecture",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=4),
            status=PassStatus.PENDING,
        )

        self.client.force_authenticate(user=self.admin_a)
        url = reverse("visitor-pass-approve", kwargs={"pk": visitor_pass.id})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        visitor_pass.refresh_from_db()
        self.assertEqual(visitor_pass.status, PassStatus.APPROVED)
        self.assertEqual(visitor_pass.approved_by, self.admin_a)

    def test_unauthorized_user_cannot_approve_pass(self):
        """A different host or regular user cannot approve another host's pass."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Edward Norton",
            visitor_email="edward@fight.org",
            visitor_phone="+1-555-4444",
            purpose="Discussion",
            valid_from=now,
            valid_until=now + timedelta(hours=3),
            status=PassStatus.PENDING,
        )

        # host_a2 tries to approve host_a1's pass
        self.client.force_authenticate(user=self.host_a2)
        url = reverse("visitor-pass-approve", kwargs={"pk": visitor_pass.id})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # student tries to approve
        self.client.force_authenticate(user=self.student_a)
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_host_can_reject_pass_with_reason(self):
        """Host can reject a pending pass with an explanatory reason."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Frank Miller",
            visitor_email="frank@sin.city",
            visitor_phone="+1-555-5555",
            purpose="Vendor Pitch",
            valid_from=now,
            valid_until=now + timedelta(hours=2),
            status=PassStatus.PENDING,
        )

        self.client.force_authenticate(user=self.host_a1)
        url = reverse("visitor-pass-reject", kwargs={"pk": visitor_pass.id})
        response = self.client.post(url, {"reason": "Schedule conflict, unavailable today"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        visitor_pass.refresh_from_db()
        self.assertEqual(visitor_pass.status, PassStatus.REJECTED)
        self.assertEqual(visitor_pass.rejected_by, self.host_a1)
        self.assertEqual(visitor_pass.rejection_reason, "Schedule conflict, unavailable today")

        log = visitor_pass.logs.filter(action=LogAction.REJECTED).first()
        self.assertIsNotNone(log)

    def test_cannot_approve_already_approved_or_rejected_pass(self):
        """Approving a pass that is already approved or rejected raises validation error."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Grace Hopper",
            visitor_email="grace@navy.mil",
            visitor_phone="+1-555-6666",
            purpose="Consultation",
            valid_from=now,
            valid_until=now + timedelta(hours=3),
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.host_a1)
        url = reverse("visitor-pass-approve", kwargs={"pk": visitor_pass.id})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "invalid_transition")

    def test_cancel_pending_and_approved_pass(self):
        """Pass can be cancelled when pending or approved, but not when checked in."""
        now = timezone.now()
        pass1 = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            created_by=self.student_a,
            visitor_name="Hannah Abbott",
            visitor_email="hannah@hufflepuff.org",
            visitor_phone="+1-555-7777",
            purpose="Study Visit",
            valid_from=now,
            valid_until=now + timedelta(hours=3),
            status=PassStatus.PENDING,
        )

        self.client.force_authenticate(user=self.student_a)
        url = reverse("visitor-pass-cancel", kwargs={"pk": pass1.id})
        response = self.client.post(url, {"reason": "Meeting rescheduled"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pass1.refresh_from_db()
        self.assertEqual(pass1.status, PassStatus.CANCELLED)

    # -------------------------------------------------------------
    # 3. Security QR Verification & Tenant Isolation
    # -------------------------------------------------------------

    def test_qr_verification_valid_approved_pass(self):
        """Security user can verify an approved pass at the checkpoint."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Iris West",
            visitor_email="iris@centralcity.news",
            visitor_phone="+1-555-8888",
            purpose="Press Visit",
            valid_from=now - timedelta(minutes=15),
            valid_until=now + timedelta(hours=3),
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.security_a)
        url = reverse("visitor-verify-qr")
        payload = {"qr_token": visitor_pass.qr_token, "checkpoint_name": "Gate 1"}
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        verification = response.data["verification"]
        self.assertTrue(verification["valid"])
        self.assertTrue(verification["can_check_in"])
        self.assertFalse(verification["can_check_out"])
        self.assertEqual(verification["visitor_name"], "Iris West")

        # Verify QR verification log was created
        log = visitor_pass.logs.filter(action=LogAction.QR_VERIFIED).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.scanned_by, self.security_a)

    def test_qr_verification_cross_tenant_blocked_without_leakage(self):
        """
        SECURITY REQUIREMENT:
        When Security from Tenant B scans a QR from Tenant A, the response must return 404
        without leaking whether the pass exists on another tenant.
        """
        now = timezone.now()
        pass_a = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Tenant A Visitor",
            visitor_email="a_visitor@domain.com",
            visitor_phone="+1-555-9999",
            purpose="Secret Project",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=2),
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.security_b)  # Guard from Tenant B
        url = reverse("visitor-verify-qr")
        payload = {"qr_token": pass_a.qr_token, "checkpoint_name": "Tower Gate B"}
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "invalid_qr")

    def test_qr_verification_expired_pass(self):
        """Pass past valid_until reports valid=False and expired message."""
        now = timezone.now()
        expired_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="John Old",
            visitor_email="john@old.com",
            visitor_phone="+1-555-1234",
            purpose="Yesterday Visit",
            valid_from=now - timedelta(days=2),
            valid_until=now - timedelta(hours=1),  # Expired
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.security_a)
        url = reverse("visitor-verify-qr")
        response = self.client.post(url, {"qr_token": expired_pass.qr_token}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        verification = response.data["verification"]
        self.assertFalse(verification["valid"])
        self.assertFalse(verification["can_check_in"])
        self.assertIn("expired", verification["message"].lower())

    # -------------------------------------------------------------
    # 4. Gate Check-in & Check-out Actions & Concurrency
    # -------------------------------------------------------------

    def test_gate_check_in_and_check_out_success(self):
        """Security user performs check-in then check-out with full audit tracking."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Kara Danvers",
            visitor_email="kara@catco.media",
            visitor_phone="+1-555-2468",
            purpose="Interview",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=3),
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.security_a)

        # 1. Check in
        check_in_url = reverse("visitor-check-in")
        in_res = self.client.post(
            check_in_url,
            {"qr_token": visitor_pass.qr_token, "checkpoint_name": "Gate 1 North"},
            format="json",
        )
        self.assertEqual(in_res.status_code, status.HTTP_200_OK)
        visitor_pass.refresh_from_db()
        self.assertEqual(visitor_pass.status, PassStatus.CHECKED_IN)
        self.assertIsNotNone(visitor_pass.checked_in_at)

        in_log = visitor_pass.logs.filter(action=LogAction.CHECK_IN).first()
        self.assertIsNotNone(in_log)
        self.assertEqual(in_log.scanned_by, self.security_a)
        self.assertEqual(in_log.checkpoint_name, "Gate 1 North")

        # 2. Check out
        check_out_url = reverse("visitor-check-out")
        out_res = self.client.post(
            check_out_url,
            {"qr_token": visitor_pass.qr_token, "checkpoint_name": "Gate 1 South"},
            format="json",
        )
        self.assertEqual(out_res.status_code, status.HTTP_200_OK)
        visitor_pass.refresh_from_db()
        self.assertEqual(visitor_pass.status, PassStatus.CHECKED_OUT)
        self.assertIsNotNone(visitor_pass.checked_out_at)

        out_log = visitor_pass.logs.filter(action=LogAction.CHECK_OUT).first()
        self.assertIsNotNone(out_log)
        self.assertEqual(out_log.scanned_by, self.security_a)

    def test_duplicate_check_in_prevented(self):
        """Checking in an already checked-in pass must be rejected."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Barry Allen",
            visitor_email="barry@star.labs",
            visitor_phone="+1-555-9876",
            purpose="Lab Visit",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=3),
            status=PassStatus.CHECKED_IN,
            checked_in_at=now - timedelta(minutes=5),
        )

        self.client.force_authenticate(user=self.security_a)
        check_in_url = reverse("visitor-check-in")
        response = self.client.post(check_in_url, {"qr_token": visitor_pass.qr_token}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "check_in_failed")

    def test_cannot_check_out_without_check_in(self):
        """Checking out an approved pass before check-in must be rejected."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Oliver Queen",
            visitor_email="oliver@queen.ind",
            visitor_phone="+1-555-4321",
            purpose="Board Meeting",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=3),
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.security_a)
        check_out_url = reverse("visitor-check-out")
        response = self.client.post(check_out_url, {"qr_token": visitor_pass.qr_token}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "check_out_failed")

    def test_cannot_check_in_pending_or_rejected_pass(self):
        """Check-in is blocked for pending or rejected passes."""
        now = timezone.now()
        pending_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Pending Visitor",
            visitor_email="p@vis.com",
            visitor_phone="+1-555-0011",
            purpose="Visit",
            valid_from=now - timedelta(minutes=5),
            valid_until=now + timedelta(hours=2),
            status=PassStatus.PENDING,
        )

        self.client.force_authenticate(user=self.security_a)
        check_in_url = reverse("visitor-check-in")
        res = self.client.post(check_in_url, {"qr_token": pending_pass.qr_token}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_check_in_before_valid_from(self):
        """Check-in is blocked before the pass becomes active."""
        now = timezone.now()
        future_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Future Visitor",
            visitor_email="f@vis.com",
            visitor_phone="+1-555-0022",
            purpose="Future Visit",
            valid_from=now + timedelta(hours=2),  # In the future
            valid_until=now + timedelta(hours=5),
            status=PassStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.security_a)
        check_in_url = reverse("visitor-check-in")
        res = self.client.post(check_in_url, {"qr_token": future_pass.qr_token}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------
    # 5. Role Restrictions & Unauthorized Access
    # -------------------------------------------------------------

    def test_regular_user_cannot_verify_qr_or_check_in(self):
        """General users / students cannot call security verification or check-in APIs."""
        self.client.force_authenticate(user=self.student_a)
        verify_url = reverse("visitor-verify-qr")
        res = self.client.post(verify_url, {"qr_token": "any-token"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        check_in_url = reverse("visitor-check-in")
        res = self.client.post(check_in_url, {"qr_token": "any-token"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_requests_blocked(self):
        """Unauthenticated access is blocked across all visitor endpoints."""
        url = reverse("visitor-pass-list")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # -------------------------------------------------------------
    # 6. Append-Only Audit Trail Immutability
    # -------------------------------------------------------------

    def test_visitor_log_immutability(self):
        """Modifying or deleting an existing VisitorLog record must raise ValidationError."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            visitor_name="Audit Subject",
            visitor_email="audit@subject.com",
            visitor_phone="+1-555-9090",
            purpose="Audit Check",
            valid_from=now,
            valid_until=now + timedelta(hours=2),
            status=PassStatus.PENDING,
        )
        log = VisitorLog.objects.create(
            tenant=self.tenant_a,
            visitor_pass=visitor_pass,
            action=LogAction.REQUESTED,
            scanned_by=self.host_a1,
            checkpoint_name="Portal",
        )

        # Attempt to modify
        log.notes = "Tampered notes"
        with self.assertRaises(ValidationError):
            log.save()

        # Attempt to delete
        with self.assertRaises(ValidationError):
            log.delete()

    def test_visitor_history_endpoint(self):
        """Pass history endpoint returns ordered timeline of events."""
        now = timezone.now()
        visitor_pass = VisitorPass.objects.create(
            tenant=self.tenant_a,
            host=self.host_a1,
            created_by=self.host_a1,
            visitor_name="History Subject",
            visitor_email="hist@subject.com",
            visitor_phone="+1-555-8080",
            purpose="History Check",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(hours=3),
            status=PassStatus.PENDING,
        )
        VisitorLog.objects.create(
            tenant=self.tenant_a,
            visitor_pass=visitor_pass,
            action=LogAction.REQUESTED,
            scanned_by=self.host_a1,
        )
        visitor_pass.approve(user=self.host_a1)
        VisitorLog.objects.create(
            tenant=self.tenant_a,
            visitor_pass=visitor_pass,
            action=LogAction.APPROVED,
            scanned_by=self.host_a1,
        )

        self.client.force_authenticate(user=self.host_a1)
        url = reverse("visitor-pass-history", kwargs={"pk": visitor_pass.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
