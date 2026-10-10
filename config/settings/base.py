import os
import sys
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR points to root repository directory: d:\cma-navi-backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Add apps folder to Python path for convenience
sys.path.insert(0, str(BASE_DIR / "apps"))

# Load .env file
load_dotenv(BASE_DIR / ".env")

import secrets
from django.core.exceptions import ImproperlyConfigured

raw_secret = os.environ.get("DJANGO_SECRET_KEY", "").strip()
env_name = os.environ.get("DJANGO_ENV", "development").lower()
is_production = env_name == "production"

if not raw_secret:
    if is_production:
        raise ImproperlyConfigured(
            "CRITICAL SECURITY ERROR: DJANGO_SECRET_KEY environment variable is missing. "
            "A secure secret key must be explicitly configured in production."
        )
    # For local development or tests without an explicit key, generate an ephemeral,
    # high-entropy key unique to this running process so no known static fallback is used.
    SECRET_KEY = secrets.token_urlsafe(50)
else:
    SECRET_KEY = raw_secret

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes") and not is_production

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
    if host.strip()
]

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.common",
    "apps.tenants",
    "apps.authentication",
    "apps.blueprints",
    "apps.visitors",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database configuration
DB_ENGINE = os.environ.get("DB_ENGINE", "django.db.backends.postgresql")
DB_NAME = os.environ.get("DB_NAME", "wayora_db")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

DATABASES = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
    }
}

# If running automated test suite and no test postgres is explicitly forced, use fast in-memory database
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    if not os.environ.get("USE_POSTGRES_FOR_TESTS"):
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        }

# Custom User Model
AUTH_USER_MODEL = "authentication.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
}

# Simple JWT Configuration
ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "60"))
REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "").strip() or SECRET_KEY

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=REFRESH_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}

# OpenAPI / Swagger via drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Wayora API",
    "DESCRIPTION": (
        "Wayora — Find Your Way. Find Your People.\n\n"
        "Multi-tenant indoor navigation and visitor pass management platform "
        "for colleges, malls, and IT parks."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1/",
}

# CORS configuration
cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if cors_origins:
    CORS_ALLOWED_ORIGINS = [
        origin.strip() for origin in cors_origins.split(",") if origin.strip()
    ]
    CORS_ALLOW_ALL_ORIGINS = False
else:
    CORS_ALLOWED_ORIGINS = []
    CORS_ALLOW_ALL_ORIGINS = DEBUG

CORS_ALLOW_CREDENTIALS = True

# Blueprint Storage Configuration (AWS S3 / Private Object Storage)
USE_S3_STORAGE = os.environ.get("USE_S3_STORAGE", "False").lower() in ("true", "1", "yes")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "wayora-blueprints")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
AWS_S3_SIGNATURE_VERSION = os.environ.get("AWS_S3_SIGNATURE_VERSION", "s3v4")
AWS_DEFAULT_ACL = os.environ.get("AWS_DEFAULT_ACL", "private")
AWS_PRESIGNED_EXPIRY_SECONDS = int(os.environ.get("AWS_PRESIGNED_EXPIRY_SECONDS", "3600"))
