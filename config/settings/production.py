import os
from django.core.exceptions import ImproperlyConfigured
from .base import *

DEBUG = False

# Strict production secret check
if not os.environ.get("DJANGO_SECRET_KEY", "").strip():
    raise ImproperlyConfigured(
        "CRITICAL: DJANGO_SECRET_KEY environment variable is missing. "
        "A strong, unique secret key is required in production."
    )

# Disallow arbitrary CORS in production
CORS_ALLOW_ALL_ORIGINS = False

# Strict production security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
