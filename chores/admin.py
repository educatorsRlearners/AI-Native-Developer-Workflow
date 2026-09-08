from django.contrib import admin

from chores.models import Chore, Completion, Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    readonly_fields = ("pin_hash", "created_at", "updated_at")


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "cadence", "anchor_date", "claimed_by")
    list_filter = ("owner", "cadence")


@admin.register(Completion)
class CompletionAdmin(admin.ModelAdmin):
    list_display = ("chore", "person", "completed_at")
    list_filter = ("person", "chore")
