from django.contrib import admin
from .models import Tenant

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tenant_type", "domain", "is_active", "created_at")
    list_filter = ("tenant_type", "is_active")
    search_fields = ("name", "slug", "domain", "contact_email")
    prepopulated_fields = {"slug": ("name",)}
