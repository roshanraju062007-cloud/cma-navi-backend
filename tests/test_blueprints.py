from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import User, UserRole
from apps.tenants.models import Tenant
from apps.blueprints.models import BlueprintMetadata

class BlueprintStorageTests(TestCase):
    """Test suite for private blueprint storage and metadata operations."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Silicon IT Park",
            slug="silicon-park",
            tenant_type="it_park",
        )
        self.admin = User.objects.create_user(
            email="admin@silicon.com",
            password="Password123!",
            role=UserRole.TENANT_ADMIN,
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
