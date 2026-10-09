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
        self.user_password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="student@apex.edu",
            password=self.user_password,
            first_name="Jane",
            last_name="Doe",
            role=UserRole.USER,
            tenant=self.tenant,
        )

    def test_user_registration_success(self):
        """Test successful registration of a new user."""
        url = reverse("auth-register")
        payload = {
            "email": "visitor@example.com",
            "password": "StrongPassword456!",
            "password_confirm": "StrongPassword456!",
            "first_name": "John",
            "last_name": "Smith",
            "phone_number": "+1234567890",
            "role": "user",
            "tenant_id": str(self.tenant.id),
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["email"], "visitor@example.com")
        self.assertTrue(User.objects.filter(email="visitor@example.com").exists())

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
