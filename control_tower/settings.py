from __future__ import annotations

import os
from pathlib import Path

import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DEBUG", "1") == "1"

_allowed_hosts = os.environ.get("ALLOWED_HOSTS")
if DEBUG:
    ALLOWED_HOSTS = ["*"]
elif _allowed_hosts:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tower.apps.TowerConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "control_tower.urls"

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
    }
]

WSGI_APPLICATION = "control_tower.wsgi.application"


DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{(BASE_DIR / 'db.sqlite3')}",
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
    )
}


AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/admin/login/"


# Live update settings (keep simple, poll-based)
LIVE_UPDATES_POLL_SECONDS = int(os.environ.get("LIVE_UPDATES_POLL_SECONDS", "5"))
MAX_DASHBOARD_SHIPMENTS = int(os.environ.get("MAX_DASHBOARD_SHIPMENTS", "10"))


# Weather integration
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
WEATHER_CACHE_TTL_SECONDS = int(os.environ.get("WEATHER_CACHE_TTL_SECONDS", "300"))

# Traffic simulation cache
TRAFFIC_CACHE_TTL_SECONDS = int(os.environ.get("TRAFFIC_CACHE_TTL_SECONDS", "180"))
