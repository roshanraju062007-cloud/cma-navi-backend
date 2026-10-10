# Wayora — Backend Integration Contracts & Architecture Alignment

> **Document Version:** 1.0.0  
> **Target Audience:** Pradeesh (Campus & Navigation), Bhuvaneshwari (Visitor Management & Group Sessions), Frontend SPA Team (TypeScript/React).  
> **Foundation Branch:** `feature/backend-foundation`

---

## 1. Foundation Capabilities & Conventions

All teammates must inherit and follow these foundational primitives:

### Base Model Hierarchy
```
BaseModel (UUIDModel + TimeStampedModel)
   └── TenantScopedModel
          ├── (Pradeesh: Campus, Building, Floor, POI, NavigationNode, NavigationEdge)
          ├── (Bhuvaneshwari: VisitorPass, VisitorLog, GroupSession, LocationConsent, SavedParking)
          └── (Foundation: BlueprintMetadata)
```

1. **Primary Keys (`UUIDModel`)**:
   - Every domain entity has a non-sequential, cryptographically secure `UUIDField` primary key (`id = uuid.uuid4`).
   - URLs follow `/api/v1/<resource>/<uuid>/`.
2. **Timestamps & Active Flag (`TimeStampedModel` / `BaseModel`)**:
   - `created_at` (DateTimeField, auto_now_add=True, db_index=True)
   - `updated_at` (DateTimeField, auto_now=True)
   - `is_active` (BooleanField, default=True, db_index=True)
3. **Multi-Tenant Isolation (`TenantScopedModel` & `TenantScopedManager`)**:
   - Every multi-tenant model inherits from `apps.tenants.models.TenantScopedModel`.
   - Provides foreign key: `tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="...")`.
   - Queries must use `Model.objects.for_user(request.user)`:
     - **Super Admins**: See all records across all tenants.
     - **Tenant Admins / Staff / Security / Users**: Strictly isolated to records matching `request.user.tenant`.
     - Cross-tenant lookups automatically raise `404 Not Found` (never leakage).
4. **API Responses & Error Envelope**:
   - **Success (List)**:
     ```json
     {
       "success": true,
       "count": 42,
       "total_pages": 3,
       "current_page": 1,
       "next": "http://.../?page=2",
       "previous": null,
       "results": [...]
     }
     ```
   - **Error**:
     ```json
     {
       "success": false,
       "error": {
         "code": "permission_denied",
         "status_code": 403,
         "message": "Human-readable explanation.",
         "details": {}
       }
     }
     ```
5. **Filtering, Search & Ordering**:
   - Globally configured `DEFAULT_FILTER_BACKENDS`:
     - `rest_framework.filters.SearchFilter` (`?search=<query>`)
     - `rest_framework.filters.OrderingFilter` (`?ordering=-created_at`)

6. **Authoritative User Roles & Permission Classes**:
   | Database String (`role`) | Enum Constant (`UserRole`) | Display Name | Corresponding Permission Class |
   |---|---|---|---|
   | `super_admin` | `UserRole.SUPER_ADMIN` | Super Admin | `apps.authentication.permissions.IsSuperAdmin` |
   | `tenant_admin` | `UserRole.TENANT_ADMIN` | Tenant Admin | `apps.authentication.permissions.IsTenantAdmin` |
   | `staff` | `UserRole.STAFF` | Staff / Faculty | `apps.authentication.permissions.IsStaffUser` |
   | `security` | `UserRole.SECURITY` | Security Personnel | `apps.authentication.permissions.IsSecurityUser` |
   | `user` | `UserRole.USER` | General User / Visitor | `rest_framework.permissions.IsAuthenticated` |

   > [!IMPORTANT]
   > The security role string in the database and JWT payload is strictly `"security"`, **never** `"security_guard"`. Bhuvaneshwari's endpoints must check `request.user.role == "security"` or utilize `IsSecurityUser` / `IsStaffOrSecurity`.

7. **Blueprint Action URLs & Router Conventions**:
   - `POST /api/v1/blueprints/request_upload_url/` (`name='blueprint-request-upload-url'`)
   - `GET /api/v1/blueprints/<uuid:id>/download_url/` (`name='blueprint-download-url'`)

---

## 2. Interface Contracts with Pradeesh (Campus & Navigation Module)

**Module Ownership:** Pradeesh owns `apps/campus/` and `apps/navigation/`.

### Shared Data Model Contracts

```python
# apps/campus/models.py
from apps.tenants.models import TenantScopedModel
from django.db import models

class Campus(TenantScopedModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, db_index=True)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    boundary_geojson = models.JSONField(null=True, blank=True)

class Building(TenantScopedModel):
    campus = models.ForeignKey(Campus, on_delete=models.CASCADE, related_name="buildings")
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    number_of_floors = models.PositiveIntegerField(default=1)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

class Floor(TenantScopedModel):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="floors")
    floor_number = models.IntegerField(help_text="e.g. -1 for basement, 0 for ground, 1 for first")
    name = models.CharField(max_length=100)
    # Link to foundation's BlueprintMetadata:
    blueprint = models.ForeignKey(
        "blueprints.BlueprintMetadata",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_floors",
    )
```

```python
# apps/navigation/models.py
from apps.tenants.models import TenantScopedModel
from django.db import models

class NodeType(models.TextChoices):
    WALKWAY = "walkway", "Walkway / Corridor"
    ELEVATOR = "elevator", "Elevator"
    STAIRS = "stairs", "Stairs"
    RAMP = "ramp", "Wheelchair Ramp"
    ENTRANCE = "entrance", "Building Entrance / Exit"
    DOOR = "door", "Room Door"
    OUTDOOR_PATH = "outdoor_path", "Outdoor Campus Pathway"

class NavigationNode(TenantScopedModel):
    floor = models.ForeignKey(
        "campus.Floor", on_delete=models.CASCADE, null=True, blank=True, related_name="nodes"
    )
    node_type = models.CharField(max_length=30, choices=NodeType.choices, default=NodeType.WALKWAY)
    x = models.FloatField(null=True, blank=True, help_text="Blueprint X coordinate (pixels or normalized 0-1)")
    y = models.FloatField(null=True, blank=True, help_text="Blueprint Y coordinate")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    label = models.CharField(max_length=100, blank=True)

class NavigationEdge(TenantScopedModel):
    from_node = models.ForeignKey(NavigationNode, on_delete=models.CASCADE, related_name="outgoing_edges")
    to_node = models.ForeignKey(NavigationNode, on_delete=models.CASCADE, related_name="incoming_edges")
    distance_meters = models.FloatField()
    is_wheelchair_accessible = models.BooleanField(default=True)
    is_bidirectional = models.BooleanField(default=True)

class PointOfInterest(TenantScopedModel):
    floor = models.ForeignKey("campus.Floor", on_delete=models.CASCADE, related_name="pois")
    nearest_node = models.ForeignKey(NavigationNode, on_delete=models.SET_NULL, null=True, related_name="pois")
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, help_text="e.g. restroom, cafeteria, lab, emergency_exit")
    x = models.FloatField()
    y = models.FloatField()
    is_accessible = models.BooleanField(default=True)
```

### Blueprint Integration Rules
- `BlueprintMetadata` in `apps/blueprints/` owns object storage and version tracking.
- Pradeesh attaches `Floor.blueprint -> BlueprintMetadata`.
- In `BlueprintMetadata`, an optional `floor_id` UUID field is provided so querying `GET /api/v1/blueprints/?floor_id=<uuid>` immediately filters floor layouts without circular foreign-key dependencies.

---

## 3. Interface Contracts with Bhuvaneshwari (Visitor Pass & Safety Module)

**Module Ownership:** Bhuvaneshwari owns `apps/visitors/` and `apps/group_sessions/`.

### Shared Data Model Contracts

```python
# apps/visitors/models.py
from django.conf import settings
from apps.tenants.models import TenantScopedModel
from django.db import models

class PassStatus(models.TextChoices):
    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CHECKED_IN = "checked_in", "Checked In"
    CHECKED_OUT = "checked_out", "Checked Out"
    EXPIRED = "expired", "Expired"

class VisitorPass(TenantScopedModel):
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_passes",
        help_text="Staff or faculty host member",
    )
    visitor_name = models.CharField(max_length=255)
    visitor_email = models.EmailField()
    visitor_phone = models.CharField(max_length=30)
    purpose = models.CharField(max_length=255)
    visit_date = models.DateField()
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(max_length=30, choices=PassStatus.choices, default=PassStatus.PENDING)
    qr_token = models.CharField(max_length=128, unique=True, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_passes",
    )

class VisitorLog(TenantScopedModel):
    visitor_pass = models.ForeignKey(VisitorPass, on_delete=models.CASCADE, related_name="logs")
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="scanned_visitor_logs",
        help_text="Security guard user",
    )
    action = models.CharField(max_length=20, choices=[("check_in", "Check In"), ("check_out", "Check Out")])
    checkpoint_name = models.CharField(max_length=100, help_text="e.g. Gate 1, Tower B Lobby")
```

```python
# apps/group_sessions/models.py
from django.conf import settings
from apps.tenants.models import TenantScopedModel
from django.db import models

class GroupSession(TenantScopedModel):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    join_code = models.CharField(max_length=8, unique=True, db_index=True)
    expires_at = models.DateTimeField()

class MemberLocationConsent(TenantScopedModel):
    group = models.ForeignKey(GroupSession, on_delete=models.CASCADE, related_name="consents")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    has_consented = models.BooleanField(default=False)
    floor_id = models.UUIDField(null=True, blank=True)
    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_ping = models.DateTimeField(auto_now=True)

class SavedParking(TenantScopedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_parking_spots")
    floor_id = models.UUIDField(null=True, blank=True)
    parking_zone = models.CharField(max_length=50, blank=True)
    spot_number = models.CharField(max_length=50, blank=True)
    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
```

### Security & Privacy Rules
- **QR Validation**: Endpoints (`POST /api/v1/visitors/verify-qr/`) must be protected by `IsSecurityUser` or `IsStaffOrSecurity`.
- **Live Location Sharing**: Live coordinates are only queryable if `has_consented == True` and `group.expires_at > now()`.
- **Tenant Isolation**: Groups are strictly tenant-isolated; users from Tenant A cannot join or view group locations in Tenant B.

---

## 4. Endpoints Inventory: Implemented vs. Planned

| Status | Method | Endpoint | Module Owner | Description | Permissions |
|---|---|---|---|---|---|
| **IMPLEMENTED** | `GET` | `/health/` | Foundation | Health check | Public |
| **IMPLEMENTED** | `POST` | `/api/v1/auth/register/` | Foundation | Public registration (strictly `user` role) | Public |
| **IMPLEMENTED** | `POST` | `/api/v1/auth/login/` | Foundation | Obtain JWT token pair + profile + tenant | Public |
| **IMPLEMENTED** | `POST` | `/api/v1/auth/refresh/` | Foundation | Refresh JWT access token | Public |
| **IMPLEMENTED** | `GET` | `/api/v1/auth/me/` | Foundation | Authenticated user profile | Authenticated |
| **IMPLEMENTED** | `PATCH` | `/api/v1/auth/me/` | Foundation | Update personal profile | Authenticated |
| **IMPLEMENTED** | `POST` | `/api/v1/auth/change-password/` | Foundation | Change password | Authenticated |
| **IMPLEMENTED** | `GET` | `/api/v1/auth/users/` | Foundation | List users (role filter: `?role=staff`) | Admin / Tenant Admin |
| **IMPLEMENTED** | `POST` | `/api/v1/auth/users/` | Foundation | Provision staff/security/user under tenant | Admin / Tenant Admin |
| **IMPLEMENTED** | `GET` | `/api/v1/tenants/` | Foundation | List tenants | Authenticated (scoped) |
| **IMPLEMENTED** | `POST` | `/api/v1/tenants/` | Foundation | Create tenant organization | `super_admin` only |
| **IMPLEMENTED** | `GET` | `/api/v1/tenants/current/` | Foundation | Get user's assigned tenant | Authenticated |
| **IMPLEMENTED** | `GET` | `/api/v1/blueprints/` | Foundation | List blueprints (`?floor_id=`, `?search=`) | Tenant Member |
| **IMPLEMENTED** | `POST` | `/api/v1/blueprints/` | Foundation | Save blueprint metadata after S3 upload | Tenant Admin |
| **IMPLEMENTED** | `POST` | `/api/v1/blueprints/request_upload_url/` | Foundation | Request presigned S3 PUT upload URL | Tenant Admin |
| **IMPLEMENTED** | `GET` | `/api/v1/blueprints/{id}/download_url/` | Foundation | Generate temporary signed download URL | Tenant Member |
| *PLANNED* | `GET/POST`| `/api/v1/campuses/` | Pradeesh | Campus management | Tenant Member / Admin |
| *PLANNED* | `GET/POST`| `/api/v1/buildings/` | Pradeesh | Building management | Tenant Member / Admin |
| *PLANNED* | `GET/POST`| `/api/v1/floors/` | Pradeesh | Floor management | Tenant Member / Admin |
| *PLANNED* | `GET/POST`| `/api/v1/pois/` | Pradeesh | Points of interest | Tenant Member / Admin |
| *PLANNED* | `POST` | `/api/v1/navigation/route/` | Pradeesh | Indoor/outdoor shortest path route | Authenticated |
| *PLANNED* | `POST` | `/api/v1/visitors/passes/` | Bhuvaneshwari | Request visitor pass | User / Staff |
| *PLANNED* | `POST` | `/api/v1/visitors/verify-qr/` | Bhuvaneshwari | Gate QR validation | `security` (`IsSecurityUser`) |
| *PLANNED* | `POST` | `/api/v1/visitors/check-in/` | Bhuvaneshwari | Gate check-in log | `security` (`IsSecurityUser`) |
| *PLANNED* | `POST` | `/api/v1/groups/` | Bhuvaneshwari | Create group session | Authenticated |
| *PLANNED* | `POST` | `/api/v1/groups/{code}/ping-location/` | Bhuvaneshwari | Update live coordinates | Group Member |
| *PLANNED* | `POST` | `/api/v1/parking/saved/` | Bhuvaneshwari | Save vehicle parking spot | Authenticated |
