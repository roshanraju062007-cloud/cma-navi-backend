from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import User, UserRole
from apps.tenants.models import Tenant

class AuthenticationTests(TestCase):
    """Test suite for user registration, JWT authentication, and profile endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Apex College of Engineering",
            slug="apex-engineering",
            tenant_type="college",
        )
        self.other_tenant = Tenant.objects.create(
            name="Metropolis IT Park",
            slug="metropolis-park",
            tenant_type="it_park",
        )
        self.user_password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="student@apex.edu",
            password=self.user_password,
            first_name="Jane",
            last_name="Doe",
            role=UserRole.USER,
            tenant=self.tenant,
        )
        self.tenant_admin = User.objects.create_user(
            email="admin@apex.edu",
            password=self.user_password,
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant,
        )
        self.super_admin = User.objects.create_superuser(
            email="superadmin@wayora.io",
            password=self.user_password,
            role=UserRole.SUPER_ADMIN,
        )

    def test_user_registration_success(self):
        """Test successful legitimate registration of a standard user."""
        url = reverse("auth-register")
        payload = {
            "email": "visitor@example.com",
            "password": "StrongPassword456!",
            "password_confirm": "StrongPassword456!",
            "first_name": "John",
            "last_name": "Smith",
            "phone_number": "+1234567890",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["email"], "visitor@example.com")
        self.assertEqual(response.data["user"]["role"], UserRole.USER)
        self.assertIsNone(response.data["user"]["tenant"])

        created_user = User.objects.get(email="visitor@example.com")
        self.assertEqual(created_user.role, UserRole.USER)
        self.assertIsNone(created_user.tenant)
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)

    def test_public_registration_privilege_escalation_blocked(self):
        """
        SECURITY REGRESSION:
        Verify that public registration rejects/ignores any attempted privileged roles
        (super_admin, tenant_admin, staff, security) and strictly creates a normal 'user'.
        """
        url = reverse("auth-register")
        malicious_roles = [
            UserRole.SUPER_ADMIN,
            UserRole.TENANT_ADMIN,
            UserRole.STAFF,
            UserRole.SECURITY,
        ]

        for idx, role in enumerate(malicious_roles):
            email = f"attacker_{idx}@example.com"
            payload = {
                "email": email,
                "password": "HackerPassword123!",
                "password_confirm": "HackerPassword123!",
                "first_name": "Malicious",
                "last_name": "Actor",
                "role": role,
            }
            response = self.client.post(url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            # User must strictly be created as standard USER
            user = User.objects.get(email=email)
            self.assertEqual(user.role, UserRole.USER)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)

    def test_public_registration_tenant_assignment_blocked(self):
        """
        SECURITY REGRESSION:
        Verify that public registration prevents self-assigning to arbitrary tenants.
        """
        url = reverse("auth-register")
        payload = {
            "email": "arbitrary_tenant@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
            "first_name": "Sneaky",
            "last_name": "User",
            "tenant_id": str(self.tenant.id),
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email="arbitrary_tenant@example.com")
        self.assertIsNone(user.tenant)

    def test_ordinary_user_cannot_create_users_via_admin_endpoint(self):
        """Ordinary users cannot access the administrative user creation endpoint."""
        self.client.force_authenticate(user=self.user)
        url = reverse("user-management-list")
        payload = {
            "email": "unauthorized_user@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
            "role": "staff",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_admin_cannot_create_super_admin(self):
        """Tenant admins cannot escalate privileges by creating super_admin accounts."""
        self.client.force_authenticate(user=self.tenant_admin)
        url = reverse("user-management-list")
        payload = {
            "email": "fake_super@apex.edu",
            "password": "Password123!",
            "password_confirm": "Password123!",
            "role": UserRole.SUPER_ADMIN,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data["error"]["details"])

    def test_tenant_admin_can_create_staff_in_own_tenant(self):
        """Tenant admins can create staff users within their assigned tenant."""
        self.client.force_authenticate(user=self.tenant_admin)
        url = reverse("user-management-list")
        payload = {
            "email": "new_faculty@apex.edu",
            "password": "FacultyPassword123!",
            "password_confirm": "FacultyPassword123!",
            "first_name": "Professor",
            "last_name": "X",
            "role": UserRole.STAFF,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        staff_user = User.objects.get(email="new_faculty@apex.edu")
        self.assertEqual(staff_user.role, UserRole.STAFF)
        self.assertEqual(staff_user.tenant, self.tenant)

    def test_registration_password_mismatch(self):
        """Test registration failure when password confirmation differs."""
        url = reverse("auth-register")
        payload = {
            "email": "mismatch@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword123!",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

    def test_jwt_login_success(self):
        """Test successful JWT login returning token pair and enriched user info."""
        url = reverse("auth-login")
        payload = {
            "email": "student@apex.edu",
            "password": self.user_password,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "student@apex.edu")
        self.assertEqual(response.data["user"]["role"], UserRole.USER)
        self.assertEqual(response.data["user"]["tenant"]["id"], str(self.tenant.id))

    def test_jwt_login_invalid_credentials(self):
        """Test login rejection on invalid password."""
        url = reverse("auth-login")
        payload = {
            "email": "student@apex.edu",
            "password": "WrongPassword",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_current_user_profile(self):
        """Test fetching the authenticated user's profile."""
        self.client.force_authenticate(user=self.user)
        url = reverse("auth-me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["email"], "student@apex.edu")
        self.assertEqual(response.data["user"]["full_name"], "Jane Doe")

    def test_change_password(self):
        """Test updating password for authenticated user."""
        self.client.force_authenticate(user=self.user)
        url = reverse("auth-change-password")
        payload = {
            "old_password": self.user_password,
            "new_password": "NewSecurePassword789!",
            "new_password_confirm": "NewSecurePassword789!",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        # Verify old password no longer works
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(self.user_password))
        self.assertTrue(self.user.check_password("NewSecurePassword789!"))
