# Wayora — Backend Foundation

> **Find Your Way. Find Your People.**  
> Multi-tenant indoor navigation and visitor pass management platform for colleges, malls, and IT parks.

---

## 1. Architecture & Technology Stack

- **Framework**: Python 3.14+ / Django 5.2 / Django REST Framework (DRF)
- **Database**: PostgreSQL (with JSON & UUID support, indexes, and full constraints)
- **Authentication**: JWT (`djangorestframework_simplejwt`) with custom role-enriched payloads for TypeScript Single Page Applications (SPAs)
- **API Documentation**: OpenAPI 3.0 / Swagger UI & ReDoc via `drf-spectacular`
- **Object Storage**: Private Object Storage (AWS S3) using secure presigned PUT/GET URLs; binary files are never stored directly in database fields or routed through Django application memory
- **Multi-Tenancy**: Tenant-isolated architecture with `TenantScopedModel` and `TenantScopedManager` base layers

---

## 2. Project Folder Structure

Following clean modular architecture and the separation of concerns:

```
d:\cma-navi-backend\
├── config/                      # Django project configuration
│   ├── settings/
│   │   ├── __init__.py          # Environment selector (development vs production)
│   │   ├── base.py              # Core settings, DRF, JWT, OpenAPI & S3 configs
│   │   ├── development.py       # Development overrides
│   │   └── production.py        # Strict production security & SSL headers
│   ├── asgi.py                  # ASGI entrypoint
│   ├── wsgi.py                  # WSGI entrypoint
│   └── urls.py                  # Root routing (/api/v1/, Swagger, Health check)
│
├── apps/                        # Pluggable domain modules
│   ├── common/                  # Shared base classes, storage, error formatting
│   │   ├── models.py            # BaseModel (UUID pk, timestamps, is_active)
│   │   ├── pagination.py        # StandardResultsSetPagination (page_size, count, links)
│   │   ├── exceptions.py        # Standardized JSON error response handler
│   │   └── storage.py           # S3 presigned URL generator & private storage provider
│   │
│   ├── tenants/                 # Multi-tenant isolation module
│   │   ├── models.py            # Tenant, TenantScopedModel, TenantScopedManager
│   │   ├── serializers.py       # Tenant CRUD serializers
│   │   ├── views.py             # TenantViewSet & /current/ endpoint
│   │   ├── permissions.py       # IsSuperAdmin, IsTenantAdmin, IsTenantMember
│   │   └── urls.py
│   │
│   ├── authentication/          # User accounts, RBAC, and JWT authentication
│   │   ├── models.py            # Custom User model (5 roles, tenant FK)
│   │   ├── serializers.py       # Register, Login, User profile, Password serializers
│   │   ├── views.py             # RegisterView, LoginView, RefreshView, CurrentUserView
│   │   ├── permissions.py       # Role-based permissions (IsSuperAdmin, IsTenantAdmin, etc.)
│   │   └── urls.py
│   │
│   └── blueprints/              # Floor blueprint storage & metadata foundation
│       ├── models.py            # BlueprintMetadata (stores S3 keys, sizes, hashes, versions)
│       ├── serializers.py       # Metadata serializers with presigned download URL
│       ├── views.py             # BlueprintViewSet, request_upload_url, download_url
│       └── urls.py
│
├── tests/                       # Automated test suite (15 tests passing)
│   ├── test_authentication.py   # Registration, JWT token pair, me profile, password change
│   ├── test_tenant_isolation.py # Data isolation across tenants & super-admin override
│   ├── test_permissions.py      # RBAC verification across 5 user roles
│   └── test_blueprints.py       # Presigned upload/download URLs & metadata storage
│
├── manage.py                    # Django management script (auto-loads .env)
├── requirements.txt             # Pinned project dependencies
├── .env.example                 # Documented environment variables template
└── .gitignore                   # Comprehensive ignore rules
```

---

## 3. Getting Started & Setup Instructions

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ (local service or remote instance)

### Step 1: Environment Setup
```bash
# Clone the repository
git clone https://github.com/roshanraju062007-cloud/cma-navi-backend.git
cd cma-navi-backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install dependencies
python -m pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` and fill in your PostgreSQL credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```ini
DJANGO_SECRET_KEY=your-secure-random-secret-key
DJANGO_DEBUG=True
DB_ENGINE=django.db.backends.postgresql
DB_NAME=wayora_db
DB_USER=postgres
DB_PASSWORD=your_actual_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

### Step 3: Run Database Migrations
Create the PostgreSQL database `wayora_db` in your PostgreSQL server, then run:
```bash
python manage.py migrate
```

### Step 4: Create a Super Administrator
```bash
python manage.py createsuperuser
```

### Step 5: Start the Development Server
```bash
python manage.py runserver
```
The server will start at `http://127.0.0.1:8000/`.

---

## 4. API Endpoints & Interactive Documentation

Interactive documentation is available out of the box:
- **Swagger UI**: `http://127.0.0.1:8000/api/v1/docs/`
- **ReDoc**: `http://127.0.0.1:8000/api/v1/redoc/`
- **OpenAPI Schema (YAML/JSON)**: `http://127.0.0.1:8000/api/v1/schema/`

### Implemented Endpoints Reference

| Method | Endpoint | Description | Permissions |
|---|---|---|---|
| `GET` | `/health/` or `/api/v1/health/` | System health check | Public |
| `POST` | `/api/v1/auth/register/` | Register new user account | Public |
| `POST` | `/api/v1/auth/login/` | Obtain JWT token pair + user info + tenant | Public |
| `POST` | `/api/v1/auth/refresh/` | Refresh expired access token | Public |
| `GET` | `/api/v1/auth/me/` | Get current authenticated user profile | Authenticated |
| `PATCH`| `/api/v1/auth/me/` | Update current user name / phone | Authenticated |
| `POST` | `/api/v1/auth/change-password/` | Change account password | Authenticated |
| `GET` | `/api/v1/auth/users/` | List users (scoped to tenant unless Super Admin) | Admin / Tenant Admin |
| `POST` | `/api/v1/auth/users/` | Create a user under current tenant | Admin / Tenant Admin |
| `GET` | `/api/v1/tenants/` | List tenant organizations | Authenticated (scoped) |
| `POST` | `/api/v1/tenants/` | Create a new tenant (college, mall, IT park) | `super_admin` only |
| `GET` | `/api/v1/tenants/{id}/` | Retrieve tenant details | Tenant Admin / Super Admin |
| `PATCH`| `/api/v1/tenants/{id}/` | Update tenant details | Tenant Admin / Super Admin |
| `GET` | `/api/v1/tenants/current/` | Get current user's tenant organization | Authenticated |
| `GET` | `/api/v1/blueprints/` | List floor blueprints (strictly tenant-scoped) | Tenant Member |
| `POST` | `/api/v1/blueprints/` | Save blueprint metadata after S3 upload | Tenant Admin |
| `POST` | `/api/v1/blueprints/request_upload_url/` | Get presigned PUT URL for client-direct upload | Tenant Admin |
| `GET` | `/api/v1/blueprints/{id}/download_url/` | Refresh presigned GET URL for viewing | Tenant Member |

---

## 5. Multi-Tenant Isolation & Role-Based Access Control (RBAC)

### User Roles Matrix

1. **`super_admin`**: Platform administrator. Can view and manage all tenants, users, and resources across the platform.
2. **`tenant_admin`**: Organization administrator (e.g., College Dean, Mall Admin). Can manage campus data, floors, blueprints, staff, and security personnel within their tenant.
3. **`staff`**: Staff or faculty member. Can issue/approve visitor passes and access indoor routing.
4. **`security`**: Gate/entrance security guards. Can validate QR codes and check visitors in/out.
5. **`user`**: General visitor or regular student/employee. Can request visitor passes and navigate floor plans.

### Tenant Isolation Architecture
All multi-tenant models inherit from `TenantScopedModel`:
- Querysets are automatically filtered using `objects.for_user(request.user)`.
- If a user belongs to Tenant A, they can **never** query or mutate records belonging to Tenant B (returns `404 Not Found`).
- Super admins automatically bypass the filter to view all tenants when needed.

---

## 6. Blueprint Object Storage Architecture

Large CAD, SVG, or high-resolution PNG blueprints are **never stored as database binary blobs** or streamed through Django web servers.

### Upload Flow:
1. Client requests a presigned upload URL:
   `POST /api/v1/blueprints/request_upload_url/` with `{ filename: "floor1.png", content_type: "image/png", title: "Floor 1" }`
2. Backend responds with an AWS S3 presigned PUT URL (or local development signed token) with a unique partitioned key:
   `blueprints/{tenant_id}/{year}/{month}/{unique_hash}_{filename}`.
3. Client uploads the binary file **directly** to private S3 storage via HTTP PUT.
4. Client notifies backend by saving metadata:
   `POST /api/v1/blueprints/` with `{ title, file_key, original_filename, file_size_bytes, mime_type, version }`.

### Download / View Flow:
- When fetching a blueprint (`GET /api/v1/blueprints/{id}/`), the backend dynamically returns a temporary, expiring presigned GET URL (`download_url`).
- Blueprint files are kept strictly private in S3 (no public read permissions).

---

## 7. Frontend Integration Guide (TypeScript)

When logging in via `POST /api/v1/auth/login/`:
```json
{
  "access": "<jwt_access_token>",
  "refresh": "<jwt_refresh_token>",
  "user": {
    "id": "11111111-2222-3333-4444-555555555555",
    "email": "admin@apex.edu",
    "full_name": "Dr. Sarah Connor",
    "role": "tenant_admin",
    "tenant": {
      "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "name": "Apex University",
      "slug": "apex-university",
      "tenant_type": "college"
    }
  }
}
```

Include the access token in all subsequent requests:
```http
Authorization: Bearer <jwt_access_token>
```

---

## 8. Team Module Integration Guide

### For Pradeesh (Campuses, Buildings, Floors, Blueprints & Navigation Routing)
- **Inherit from `TenantScopedModel`**: All campus and navigation models (`Campus`, `Building`, `Floor`, `POI`, `NavigationNode`, `NavigationEdge`) should inherit from `apps.tenants.models.TenantScopedModel`.
  ```python
  from apps.tenants.models import TenantScopedModel

  class Campus(TenantScopedModel):
      name = models.CharField(max_length=255)
      code = models.CharField(max_length=50)
  ```
- **Blueprint Association**: Link `Floor` models to `apps.blueprints.models.BlueprintMetadata`:
  ```python
  from apps.blueprints.models import BlueprintMetadata

  class Floor(TenantScopedModel):
      building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="floors")
      floor_number = models.IntegerField()
      blueprint = models.ForeignKey(
          BlueprintMetadata, on_delete=models.SET_NULL, null=True, blank=True, related_name="floors"
      )
  ```
- **Permission Checking**: Use `IsTenantMember` and `IsTenantAdmin` from `apps.tenants.permissions`.

### For Bhuvaneshwari (Visitor Pass Management, QR Validation, Check-in/out)
- **Inherit from `TenantScopedModel`**: All visitor models (`VisitorPass`, `VisitorLog`, `PassRequest`) should inherit from `TenantScopedModel`.
- **User References**: Link to `settings.AUTH_USER_MODEL`:
  ```python
  from django.conf import settings
  from apps.tenants.models import TenantScopedModel

  class VisitorPass(TenantScopedModel):
      host = models.ForeignKey(
          settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hosted_passes"
      )
      visitor_name = models.CharField(max_length=255)
      qr_code_hash = models.CharField(max_length=128, unique=True)
      status = models.CharField(max_length=30, choices=PassStatus.choices)
  ```
- **Security Checkpoints**: Guard validation endpoints with `IsSecurityUser` or `IsStaffOrSecurity` from `apps.authentication.permissions`.

---

## 9. Automated Test Results

Run the automated test suite at any time:
```bash
python manage.py test tests
```

### Verified Test Suite (15/15 passing):
- `tests.test_authentication.AuthenticationTests`:
  - `test_user_registration_success` (PASS)
  - `test_registration_password_mismatch` (PASS)
  - `test_jwt_login_success` (PASS)
  - `test_jwt_login_invalid_credentials` (PASS)
  - `test_get_current_user_profile` (PASS)
  - `test_change_password` (PASS)
- `tests.test_tenant_isolation.TenantIsolationTests`:
  - `test_user_a_only_sees_tenant_a_blueprints` (PASS)
  - `test_user_b_cannot_retrieve_tenant_a_blueprint` (PASS)
  - `test_tenant_admin_a_only_sees_tenant_a_users` (PASS)
  - `test_super_admin_can_access_all_tenant_blueprints` (PASS)
  - `test_current_tenant_endpoint` (PASS)
- `tests.test_permissions.RolePermissionsTests`:
  - `test_only_super_admin_can_create_tenants` (PASS)
  - `test_tenant_admin_can_request_blueprint_upload_url` (PASS)
- `tests.test_blueprints.BlueprintStorageTests`:
  - `test_request_presigned_upload_url` (PASS)
  - `test_create_and_retrieve_blueprint_metadata` (PASS)
