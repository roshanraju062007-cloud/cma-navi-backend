from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import User, UserRole
from apps.tenants.models import Tenant
from apps.blueprints.models import BlueprintMetadata

class BlueprintStorageTests(TestCase):
    """Test suite for private blueprint storage, authorization, and validation."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Silicon IT Park",
            slug="silicon-park",
            tenant_type="it_park",
        )
        self.other_tenant = Tenant.objects.create(
            name="Metropolis Hub",
            slug="metropolis-hub",
            tenant_type="it_park",
        )
        self.admin = User.objects.create_user(
            email="admin@silicon.com",
            password="Password123!",
            role=UserRole.TENANT_ADMIN,
            tenant=self.tenant,
        )
        self.regular_user = User.objects.create_user(
            email="user@silicon.com",
            password="Password123!",
            role=UserRole.USER,
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=self.admin)

    def test_request_presigned_upload_url(self):
        """Test generation of presigned upload URL."""
        url = reverse("blueprint-request-upload-url")
        payload = {
            "filename": "block_a_ground.png",
            "content_type": "image/png",
            "title": "Block A Ground Floor",
            "version": 1,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("upload_url", response.data["upload"])
        self.assertIn("file_key", response.data["upload"])
        self.assertTrue(response.data["upload"]["file_key"].startswith(f"blueprints/{self.tenant.id}"))

    def test_regular_user_cannot_request_upload_url(self):
        """Regular users are forbidden from generating upload URLs."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("blueprint-request-upload-url")
        payload = {
            "filename": "floorplan.png",
            "content_type": "image/png",
            "title": "Unauthorized Upload",
            "version": 1,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_disallowed_file_extension_rejected(self):
        """Uploading dangerous or non-blueprint file types is rejected."""
        url = reverse("blueprint-request-upload-url")
        payload = {
            "filename": "malicious_script.exe",
            "content_type": "application/x-msdownload",
            "title": "Malware Executable",
            "version": 1,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_content_type_rejected(self):
        """Unsupported MIME types are rejected."""
        url = reverse("blueprint-request-upload-url")
        payload = {
            "filename": "floorplan.png",
            "content_type": "text/html",
            "title": "HTML Injected File",
            "version": 1,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_tenant_key_hijacking_blocked(self):
        """Tenant Admin cannot register a blueprint pointing to another tenant's storage key."""
        url = reverse("blueprint-list")
        payload = {
            "title": "Hijacked Blueprint",
            "file_key": f"blueprints/{self.other_tenant.id}/2026/10/secret_floor.png",
            "original_filename": "secret_floor.png",
            "file_size_bytes": 1048576,
            "mime_type": "image/png",
            "version": 1,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file_key", response.data["error"]["details"])

    def test_path_traversal_in_file_key_rejected(self):
        """Directory traversal sequences in file_key are strictly rejected."""
        url = reverse("blueprint-list")
        payload = {
            "title": "Traversal Attack",
            "file_key": f"blueprints/{self.tenant.id}/../../etc/passwd",
            "original_filename": "passwd",
            "file_size_bytes": 1024,
            "mime_type": "image/png",
            "version": 1,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_and_retrieve_blueprint_metadata(self):
        """Test registering blueprint metadata and retrieving presigned download URL."""
        url = reverse("blueprint-list")
        payload = {
            "title": "Block B 1st Floor",
            "file_key": f"blueprints/{self.tenant.id}/2026/10/block_b_1st.png",
            "original_filename": "block_b_1st.png",
            "file_size_bytes": 1048576,
            "mime_type": "image/png",
            "version": 1,
        }
        create_resp = self.client.post(url, payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        blueprint_id = create_resp.data["id"]

        # Retrieve blueprint
        detail_url = reverse("blueprint-detail", kwargs={"pk": blueprint_id})
        get_resp = self.client.get(detail_url)
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(get_resp.data["title"], "Block B 1st Floor")
        self.assertIsNotNone(get_resp.data["download_url"])
        self.assertIn("download_url", get_resp.data["download_url"])
