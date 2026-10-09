from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import User, UserRole
from apps.tenants.models import Tenant

class RolePermissionsTests(TestCase):
    """
    Test suite for verifying Role-Based Access Control (RBAC):
    - super_admin
    - tenant_admin
    - staff
    - security
    - user
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Orion Mall",
            slug="orion-mall",
            tenant_type="mall",
        )

        self.super_admin = User.objects.create_superuser(
            email="superadmin@wayora.io",
            password="Password123!",
            role=UserRole.SUPER_ADMIN,
        )
        self.tenant_admin = User.objects.create_user(
            email="admin@orion.com",
            password="Password123!",
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant,
        )
        self.staff_user = User.objects.create_user(
            email="staff@orion.com",
            password="Password123!",
            role=UserRole.STAFF,
            tenant=self.tenant,
        )
        self.security_user = User.objects.create_user(
            email="guard@orion.com",
            password="Password123!",
            role=UserRole.SECURITY,
            tenant=self.tenant,
        )
        self.regular_user = User.objects.create_user(
            email="shopper@orion.com",
            password="Password123!",
            role=UserRole.USER,
            tenant=self.tenant,
        )

    def test_only_super_admin_can_create_tenants(self):
        """Creating a new tenant organization requires super_admin role."""
        url = reverse("tenant-list")
        payload = {
            "name": "New Tech Campus",
            "slug": "new-tech-campus",
            "tenant_type": "college",
        }

        # Regular user denied
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Tenant admin denied
        self.client.force_authenticate(user=self.tenant_admin)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Super admin allowed
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Tech Campus")

    def test_tenant_admin_can_request_blueprint_upload_url(self):
        """Tenant admin has permission to request presigned blueprint upload URLs."""
        url = reverse("blueprint-request-upload-url")
        payload = {
            "filename": "level_2_floorplan.svg",
            "content_type": "image/svg+xml",
            "title": "Level 2 Floorplan",
            "version": 1,
        }

        # Tenant Admin allowed
        self.client.force_authenticate(user=self.tenant_admin)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("upload_url", response.data["upload"])

        # Regular user denied
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
