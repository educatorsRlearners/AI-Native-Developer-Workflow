"""Service functions for completing and claiming chores.

Every write path here is wrapped in ``transaction.atomic`` and takes a row lock
on the chore (``select_for_update``) so concurrent completes/claims serialise.

Imports are limited to ``chores.models``, ``chores.recurrence``,
``django.db.transaction`` and ``django.utils.timezone``. No views, templates,
urls or settings.
"""

from django.db import transaction
from django.utils import timezone

from chores.models import Chore, Completion


class ChoreClaimError(ValueError):
    """Raised when a chore cannot be claimed (it has a permanent owner)."""


def last_completed_on(chore):
    """Return the local calendar date of the chore's most recent completion.

    "Most recent" is by ``completed_at`` (matching ``Completion.Meta.ordering``),
    not by insertion order. Returns ``None`` when the chore has no completions.
    """
    latest = chore.completions.order_by("-completed_at", "-id").first()
    if latest is None:
        return None
    return timezone.localtime(latest.completed_at).date()


@transaction.atomic
def complete_chore(chore, person, when=None):
    """Log a completion for ``chore`` by ``person`` and release any claim.

    Creates exactly one ``Completion`` row per call (it is an event log, not a
    toggle). ``completed_at`` is ``when`` when provided, else ``timezone.now()``.
    A timezone-naive ``when`` raises ``ValueError``. Past/future ``when`` values
    are stored as given. The chore's ``owner`` is never touched.
    """
    if when is not None and timezone.is_naive(when):
        raise ValueError("when must be timezone-aware, got a naive datetime")

    locked = Chore.objects.select_for_update().get(pk=chore.pk)

    completion = Completion.objects.create(
        chore=locked,
        person=person,
        completed_at=when if when is not None else timezone.now(),
    )

    locked.claimed_by = None
    locked.claimed_at = None
    locked.save(update_fields=["claimed_by", "claimed_at"])

    return completion


@transaction.atomic
def claim_chore(chore, person):
    """Claim a pooled chore for ``person``; last claim wins.

    Raises ``ChoreClaimError`` (a ``ValueError`` subclass) when the chore has a
    permanent ``owner``. Re-claiming an already-claimed pooled chore reassigns
    ``claimed_by`` and refreshes ``claimed_at``. Does not create a ``Completion``.
    """
    locked = Chore.objects.select_for_update().get(pk=chore.pk)

    if locked.owner is not None:
        raise ChoreClaimError(
            f"Chore {locked.title!r} has a permanent owner and cannot be claimed"
        )

    locked.claimed_by = person
    locked.claimed_at = timezone.now()
    locked.save(update_fields=["claimed_by", "claimed_at"])

    locked.refresh_from_db()
    return locked
