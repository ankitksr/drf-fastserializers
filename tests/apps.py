"""Tests-as-app config so Django can discover the synthetic models below."""

from django.apps import AppConfig


class TestsConfig(AppConfig):
    name = "tests"
    label = "tests"
    default_auto_field = "django.db.models.AutoField"
