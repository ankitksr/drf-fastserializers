"""Synthetic Django models used by from_model tests. No real data."""

from django.db import models


class MockCoop(models.Model):
    """Stand-in target for ForeignKey resolution in tests."""

    name = models.CharField(max_length=64)

    class Meta:
        app_label = "tests"


class MockTxn(models.Model):
    """Wide-shaped synthetic model exercising every from_model code path."""

    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    txn_date = models.DateField()
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict)
    coop = models.ForeignKey(MockCoop, on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = "tests"
