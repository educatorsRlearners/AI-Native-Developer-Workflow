from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models


class Person(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    pin_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin):
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return self.name


class Chore(models.Model):
    class Cadence(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        CUSTOM = "CUSTOM", "Custom"

    title = models.CharField(max_length=200)
    owner = models.ForeignKey(
        Person,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_chores",
    )
    cadence = models.CharField(max_length=10, choices=Cadence.choices)
    custom_interval_days = models.PositiveIntegerField(null=True, blank=True)
    anchor_date = models.DateField()

    def clean(self):
        if self.cadence == self.Cadence.CUSTOM and self.custom_interval_days is None:
            raise ValidationError(
                {"custom_interval_days": "Required when cadence is CUSTOM."}
            )
        if self.cadence != self.Cadence.CUSTOM and self.custom_interval_days is not None:
            raise ValidationError(
                {"custom_interval_days": "Only allowed when cadence is CUSTOM."}
            )

    @property
    def is_pooled(self):
        return self.owner is None

    def __str__(self):
        return self.title
