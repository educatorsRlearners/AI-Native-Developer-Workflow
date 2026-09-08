"""Read-only chore list page with recent activity.

Next-due / overdue state is read through :mod:`chores.recurrence`; last-completed
through :func:`chores.services.last_completed_on`. There is no ``next_due``
column and no recurrence math in this module.
"""

from django.shortcuts import render
from django.utils import timezone

from chores import recurrence
from chores.models import Chore, Completion
from chores.services import last_completed_on

RECENT_ACTIVITY_LIMIT = 10


def _cadence_label(chore):
    if chore.cadence == Chore.Cadence.CUSTOM:
        return f"Every {chore.custom_interval_days} days"
    return Chore.Cadence(chore.cadence).label


def _build_row(chore, today):
    last = last_completed_on(chore)
    due = recurrence.next_due(
        chore.cadence, chore.anchor_date, last, chore.custom_interval_days
    )
    overdue = recurrence.is_overdue(due, today)
    return {
        "title": chore.title,
        "cadence_label": _cadence_label(chore),
        "last_completed": last,
        "next_due": due,
        "is_overdue": overdue,
        "is_due_today": due == today and not overdue,
        "claimed_by_name": (
            chore.claimed_by.name
            if chore.is_pooled and chore.claimed_by is not None
            else None
        ),
    }


def chore_list(request):
    today = timezone.localdate()

    chores = Chore.objects.select_related("owner", "claimed_by").prefetch_related(
        "completions"
    )

    owner_groups = {}
    pool_rows = []
    for chore in chores:
        row = _build_row(chore, today)
        if chore.owner is None:
            pool_rows.append(row)
        else:
            owner_groups.setdefault(chore.owner.name, []).append(row)

    groups = []
    for name in sorted(owner_groups, key=str.casefold):
        rows = sorted(owner_groups[name], key=lambda r: r["title"].casefold())
        groups.append({"heading": name, "rows": rows})
    if pool_rows:
        groups.append(
            {
                "heading": "Pool",
                "rows": sorted(pool_rows, key=lambda r: r["title"].casefold()),
            }
        )

    completions = list(
        Completion.objects.select_related("chore", "person")[:RECENT_ACTIVITY_LIMIT]
    )
    activity = [
        {
            "chore_title": c.chore.title,
            "person_name": c.person.name,
            "completed_at": timezone.localtime(c.completed_at),
        }
        for c in completions
    ]

    context = {
        "groups": groups,
        "has_chores": chores.exists(),
        "activity": activity,
    }
    return render(request, "chores/chore_list.html", context)
