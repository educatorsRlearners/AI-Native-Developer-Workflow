from typing import ClassVar

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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


class PushSubscription(models.Model):
    """One browser's Web Push subscription, owned by the current person.

    Rows are created by the browser (see ``chores/static/chores/push.js`` and
    the ``chores:push-subscribe`` endpoint), never by hand. ``endpoint`` is
    globally unique -- the same browser re-subscribing upserts this row rather
    than adding a second one.
    """

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def _endpoint_host(self):
        from urllib.parse import urlparse

        return urlparse(self.endpoint).netloc or self.endpoint[:40]

    def __str__(self):
        return f"{self.person.name} @ {self._endpoint_host()}"


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
    claimed_by = models.ForeignKey(
        Person,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_chores",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

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


class Completion(models.Model):
    chore = models.ForeignKey(
        Chore,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="completions",
    )
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering: ClassVar[list[str]] = ["-completed_at", "-id"]

    def __str__(self):
        return (
            f"{self.chore} by {self.person} on {self.completed_at:%Y-%m-%d}"
        )
