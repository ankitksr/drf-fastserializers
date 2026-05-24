"""Minimal Django settings for running benchmarks."""

SECRET_KEY = "bench-not-secret"  # noqa: S105
INSTALLED_APPS = ["rest_framework"]
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
