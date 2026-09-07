from django.contrib import admin

from chores.models import Chore, Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    readonly_fields = ("pin_hash", "created_at", "updated_at")


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "cadence", "anchor_date")
    list_filter = ("owner", "cadence")
