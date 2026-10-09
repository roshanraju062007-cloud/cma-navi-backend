# Wayora — Backend Foundation

> **Find Your Way. Find Your People.**  
> Multi-tenant indoor navigation and visitor pass management platform for colleges, malls, and IT parks.

---

## 1. Architecture & Technology Stack

- **Framework**: Python 3.11+ / Django 5.2 / Django REST Framework (DRF)
- **Database**: PostgreSQL (UUID primary keys, full relational constraints, indexes)
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
│   │   ├── serializers.py       # Public & Admin user serializers, JWT login
│   │   ├── views.py             # RegisterView, LoginView, RefreshView, UserManagementViewSet
│   │   ├── permissions.py       # Role-based permissions (IsSuperAdmin, IsTenantAdmin, CanManageUser)
│   │   └── urls.py
│   │
│   └── blueprints/              # Floor blueprint storage & metadata foundation
│       ├── models.py            # BlueprintMetadata (stores S3 keys, sizes, hashes, versions)
│       ├── serializers.py       # Metadata serializers with presigned download URL & validation
│       ├── views.py             # BlueprintViewSet, request_upload_url, download_url
│       └── urls.py
│
├── tests/                       # Automated test suite (28 tests passing on PostgreSQL & SQLite)
│   ├── test_authentication.py   # Registration privilege escalation tests, JWT, user management
│   ├── test_tenant_isolation.py # Data isolation across tenants & cross-tenant defense
│   ├── test_permissions.py      # RBAC verification across 5 user roles
│   └── test_blueprints.py       # Presigned upload/download URLs & storage security tests
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

## 4. Security Hardening & Isolation Architecture

### 1. Privilege Escalation Prevention in Registration
- **Public Self-Registration (`POST /api/v1/auth/register/`)**:
  - Unconditionally forces `role = UserRole.USER` and `tenant = None`.
  - Strips and completely ignores any caller-supplied `role` or `tenant_id`.
  - Self-registering users can never grant themselves elevated roles or associate themselves with unauthorized tenants.
- **Administrative User Provisioning (`POST /api/v1/auth/users/`)**:
  - Accessible only to authorized administrators (`Tenant Admin` or `Super Admin`).
  - `Tenant Admin` can only provision non-administrative accounts (`staff`, `security`, `user`) strictly bound to their own tenant.
  - `Super Admin` can provision accounts with any role across any tenant.

### 2. Secret Key & Cryptographic Signing Security
- `DJANGO_SECRET_KEY` has no static, hardcoded fallback.
- In production, missing `DJANGO_SECRET_KEY` raises `django.core.exceptions.ImproperlyConfigured`.
- In local development without an explicit `.env` key, an ephemeral, unique cryptographic key (`secrets.token_urlsafe(50)`) is generated at runtime.
- SimpleJWT is configured with `SIGNING_KEY = JWT_SIGNING_KEY or SECRET_KEY`.

### 3. Blueprint Storage Security & Path Traversal Defenses
- Files are strictly validated:
  - Allowed extensions: `.png`, `.jpg`, `.jpeg`, `.svg`, `.pdf`, `.webp`, `.dwg`.
  - Allowed MIME types: `image/png`, `image/jpeg`, `image/svg+xml`, `application/pdf`, `image/webp`.
  - File size limit: 50 MB ceiling.
- **Path Traversal Defense**: All filenames and storage keys are sanitized via regex, and local storage resolution enforces `Path.resolve().is_relative_to(media_root)`. Any directory traversal sequence (`../`) is blocked with `403 Forbidden`.
- **Cross-Tenant Key Hijacking Prevention**: Metadata registration enforces that `file_key` strictly begins with `blueprints/{user.tenant_id}/`.

### 4. CORS Configuration
- In production (`DJANGO_ENV=production`), `CORS_ALLOW_ALL_ORIGINS = False` is strictly enforced.
- Only origins explicitly specified in `CORS_ALLOWED_ORIGINS` are accepted.

---

## 5. API Endpoints & Interactive Documentation

Interactive documentation is available out of the box:
- **Swagger UI**: `http://127.0.0.1:8000/api/v1/docs/`
- **ReDoc**: `http://127.0.0.1:8000/api/v1/redoc/`
- **OpenAPI Schema (YAML/JSON)**: `http://127.0.0.1:8000/api/v1/schema/`

### Implemented Endpoints Reference

| Method | Endpoint | Description | Permissions |
|---|---|---|---|
| `GET` | `/health/` or `/api/v1/health/` | System health check | Public |
| `POST` | `/api/v1/auth/register/` | Register standard user account (strictly `user` role) | Public |
| `POST` | `/api/v1/auth/login/` | Obtain JWT token pair + user info + tenant | Public |
| `POST` | `/api/v1/auth/refresh/` | Refresh expired access token | Public |
| `GET` | `/api/v1/auth/me/` | Get current authenticated user profile | Authenticated |
| `PATCH`| `/api/v1/auth/me/` | Update current user name / phone | Authenticated |
| `POST` | `/api/v1/auth/change-password/` | Change account password | Authenticated |
| `GET` | `/api/v1/auth/users/` | List users (scoped to tenant unless Super Admin) | Admin / Tenant Admin |
| `POST` | `/api/v1/auth/users/` | Create a user under current tenant with role validation | Admin / Tenant Admin |
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

## 6. Testing & PostgreSQL Verification

### Option A: Fast Test Runner (In-Memory SQLite)
```bash
python manage.py test tests
```

### Option B: Real PostgreSQL Verification Suite
Set `USE_POSTGRES_FOR_TESTS=1` and ensure `DB_PASSWORD` is configured:
```powershell
# Windows PowerShell:
$env:USE_POSTGRES_FOR_TESTS="1"; $env:DB_PASSWORD="postgres"; python manage.py test tests

# Linux / macOS:
USE_POSTGRES_FOR_TESTS=1 DB_PASSWORD=postgres python manage.py test tests
```

### Verified Test Results (28 / 28 PASSING on PostgreSQL 18 & SQLite):
- **Authentication & Security Regression Tests** (`tests/test_authentication.py`):
  - `test_user_registration_success` (PASS)
  - `test_public_registration_privilege_escalation_blocked` (PASS)
  - `test_public_registration_tenant_assignment_blocked` (PASS)
  - `test_ordinary_user_cannot_create_users_via_admin_endpoint` (PASS)
  - `test_tenant_admin_cannot_create_super_admin` (PASS)
  - `test_tenant_admin_can_create_staff_in_own_tenant` (PASS)
  - `test_registration_password_mismatch` (PASS)
  - `test_jwt_login_success` (PASS)
  - `test_jwt_login_invalid_credentials` (PASS)
  - `test_get_current_user_profile` (PASS)
  - `test_change_password` (PASS)
- **Tenant Isolation & Cross-Tenant Defense** (`tests/test_tenant_isolation.py`):
  - `test_user_a_only_sees_tenant_a_blueprints` (PASS)
  - `test_user_b_cannot_retrieve_tenant_a_blueprint` (PASS)
  - `test_tenant_admin_a_only_sees_tenant_a_users` (PASS)
  - `test_super_admin_can_access_all_tenant_blueprints` (PASS)
  - `test_current_tenant_endpoint` (PASS)
  - `test_tenant_admin_cannot_update_other_tenant` (PASS)
  - `test_user_cannot_obtain_download_url_for_other_tenant_blueprint` (PASS)
  - `test_unauthenticated_requests_blocked` (PASS)
- **Role-Based Access Control** (`tests/test_permissions.py`):
  - `test_only_super_admin_can_create_tenants` (PASS)
  - `test_tenant_admin_can_request_blueprint_upload_url` (PASS)
- **Blueprint Storage & Validation** (`tests/test_blueprints.py`):
  - `test_request_presigned_upload_url` (PASS)
  - `test_regular_user_cannot_request_upload_url` (PASS)
  - `test_disallowed_file_extension_rejected` (PASS)
  - `test_unsupported_content_type_rejected` (PASS)
  - `test_cross_tenant_key_hijacking_blocked` (PASS)
  - `test_path_traversal_in_file_key_rejected` (PASS)
  - `test_create_and_retrieve_blueprint_metadata` (PASS)

---

## 7. Team Integration Architecture Contracts

The foundation is built to accommodate upcoming modules seamlessly:

### 1. Navigation & Campuses (Pradeesh)
- **Campuses, Buildings, Floors, POIs, Graph Nodes, Edges, Route Calculation**:
  - Inherit all models from [`apps.tenants.models.TenantScopedModel`](file:///d:/cma-navi-backend/apps/tenants/models.py).
  - Link `Floor` models to [`apps.blueprints.models.BlueprintMetadata`](file:///d:/cma-navi-backend/apps/blueprints/models.py).
  - Guard views with `IsTenantMember` for read/navigation, and `IsTenantAdmin` for campus creation/updates.

### 2. Visitor Passes & Checkpoints (Bhuvaneshwari)
- **Visitor Passes, Approvals, QR Validation, Check-in/out, History**:
  - Inherit from [`apps.tenants.models.TenantScopedModel`](file:///d:/cma-navi-backend/apps/tenants/models.py).
  - Use `settings.AUTH_USER_MODEL` for foreign keys (`host`, `checked_in_by`).
  - Guard QR scanning and gate check-in/out with [`IsSecurityUser`](file:///d:/cma-navi-backend/apps/authentication/permissions.py) and [`IsStaffOrSecurity`](file:///d:/cma-navi-backend/apps/authentication/permissions.py).

### 3. Group Sessions & Consent-based Location Sharing
- Future `GroupSession` and `LocationShareConsent` models will inherit from `TenantScopedModel` and link to `settings.AUTH_USER_MODEL`.
- Tenant boundary guarantees that members in Campus A cannot share locations into Campus B.

### 4. Saved Parking Locations
- Future `SavedParking` models will inherit from `TenantScopedModel` with `user = ForeignKey(settings.AUTH_USER_MODEL)` and coordinates/floor ID.
