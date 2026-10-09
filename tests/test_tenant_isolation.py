from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import User, UserRole
from apps.tenants.models import Tenant
from apps.blueprints.models import BlueprintMetadata

class TenantIsolationTests(TestCase):
    """
    Test suite for verifying multi-tenant data isolation and role boundaries.
    Ensures that Tenant A users cannot read, create, update, or delete Tenant B data.
    """

    def setUp(self):
        self.client = APIClient()

        # Create two distinct tenants
        self.tenant_a = Tenant.objects.create(
            name="Alpha University",
            slug="alpha-univ",
            tenant_type="college",
        )
        self.tenant_b = Tenant.objects.create(
            name="Beta Tech Park",
            slug="beta-tech",
            tenant_type="it_park",
        )

        # Create Super Admin
        self.super_admin = User.objects.create_superuser(
            email="superadmin@wayora.io",
            password="AdminPassword123!",
            role=UserRole.SUPER_ADMIN,
        )

        # Create Tenant Admins
        self.admin_a = User.objects.create_user(
            email="admin@alpha.edu",
            password="Password123!",
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant_a,
        )
        self.admin_b = User.objects.create_user(
            email="admin@beta.com",
            password="Password123!",
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant_b,
        )

        # Create Regular Users
        self.user_a = User.objects.create_user(
            email="student@alpha.edu",
            password="Password123!",
            role=UserRole.USER,
            tenant=self.tenant_a,
        )
        self.user_b = User.objects.create_user(
            email="employee@beta.com",
            password="Password123!",
            role=UserRole.USER,
            tenant=self.tenant_b,
        )

        # Create Blueprints in Tenant A and Tenant B
        self.blueprint_a = BlueprintMetadata.objects.create(
            tenant=self.tenant_a,
            title="Alpha Main Building - Floor 1",
            file_key="blueprints/alpha/floor1.png",
            original_filename="floor1.png",
            uploaded_by=self.admin_a,
        )
        self.blueprint_b = BlueprintMetadata.objects.create(
            tenant=self.tenant_b,
            title="Beta Tower A - Ground Floor",
            file_key="blueprints/beta/tower_a_ground.png",
            original_filename="tower_a_ground.png",
            uploaded_by=self.admin_b,
        )

    def test_user_a_only_sees_tenant_a_blueprints(self):
        """User A should only see blueprints belonging to Tenant A."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse("blueprint-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]
        blueprint_ids = [item["id"] for item in results]
        self.assertIn(str(self.blueprint_a.id), blueprint_ids)
        self.assertNotIn(str(self.blueprint_b.id), blueprint_ids)

    def test_user_b_cannot_retrieve_tenant_a_blueprint(self):
        """User B must be blocked from accessing Tenant A's blueprint by ID."""
        self.client.force_authenticate(user=self.user_b)
        url = reverse("blueprint-detail", kwargs={"pk": str(self.blueprint_a.id)})
        response = self.client.get(url)
        # Should return 404 because TenantScopedManager filters it out of the queryset
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_tenant_admin_a_only_sees_tenant_a_users(self):
        """Tenant A admin should only see users in Tenant A."""
        self.client.force_authenticate(user=self.admin_a)
        url = reverse("user-management-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        emails = [item["email"] for item in response.data["results"]]
        self.assertIn("student@alpha.edu", emails)
        self.assertIn("admin@alpha.edu", emails)
        self.assertNotIn("employee@beta.com", emails)
        self.assertNotIn("admin@beta.com", emails)

    def test_super_admin_can_access_all_tenant_blueprints(self):
        """Super Admin has global override visibility across all tenants."""
        self.client.force_authenticate(user=self.super_admin)
        url = reverse("blueprint-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        blueprint_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(str(self.blueprint_a.id), blueprint_ids)
        self.assertIn(str(self.blueprint_b.id), blueprint_ids)

    def test_current_tenant_endpoint(self):
        """Verify /api/v1/tenants/current/ returns accurate tenant for logged-in user."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse("tenant-current")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tenant"]["name"], "Alpha University")

    def test_tenant_admin_cannot_update_other_tenant(self):
        """Tenant A admin cannot modify Tenant B's metadata."""
        self.client.force_authenticate(user=self.admin_a)
        url = reverse("tenant-detail", kwargs={"pk": str(self.tenant_b.id)})
        payload = {"name": "Hacked Tenant Name"}
        response = self.client.patch(url, payload, format="json")
        # TenantScoped queryset excludes other tenants, returning 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_obtain_download_url_for_other_tenant_blueprint(self):
        """User A cannot request a temporary download URL for Tenant B's blueprint."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse("blueprint-download-url", kwargs={"pk": str(self.blueprint_b.id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_requests_blocked(self):
        """Unauthenticated requests cannot access protected tenant or blueprint resources."""
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(reverse("tenant-list")).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(reverse("blueprint-list")).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(reverse("user-management-list")).status_code, status.HTTP_401_UNAUTHORIZED)
