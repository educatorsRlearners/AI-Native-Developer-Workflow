from django.contrib import admin

from chores.models import (
    Chore,
    Completion,
    Person,
    PinLockout,
    PushSubscription,
)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    readonly_fields = ("pin_hash", "created_at", "updated_at")


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "cadence", "anchor_date", "claimed_by")
    list_filter = ("owner", "cadence")


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    """Read-only: subscriptions are created by the browser, not by hand."""

    list_display = ("person", "user_agent", "created_at", "updated_at")
    list_filter = ("person",)
    readonly_fields = (
        "person",
        "endpoint",
        "p256dh",
        "auth",
        "user_agent",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PinLockout)
class PinLockoutAdmin(admin.ModelAdmin):
    """Read-only: rows are written by the sign-in flow (#14), not by hand.

    A locked-out person is released automatically once ``locked_until`` passes;
    the "Clear selected lockouts" action is the optional early manual release.
    """

    list_display = (
        "person",
        "ip_address",
        "failure_count",
        "last_failure_at",
        "locked_until",
        "is_currently_locked",
    )
    list_filter = ("person",)
    readonly_fields = (
        "person",
        "ip_address",
        "failure_count",
        "first_failure_at",
        "last_failure_at",
        "locked_until",
        "is_currently_locked",
    )
    actions = ("clear_selected_lockouts",)

    @admin.display(boolean=True, description="Currently locked")
    def is_currently_locked(self, obj):
        return obj.is_currently_locked

    @admin.action(description="Clear selected lockouts")
    def clear_selected_lockouts(self, request, queryset):
        queryset.delete()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Completion)
class CompletionAdmin(admin.ModelAdmin):
    list_display = ("chore", "person", "completed_at")
    list_filter = ("person", "chore")
