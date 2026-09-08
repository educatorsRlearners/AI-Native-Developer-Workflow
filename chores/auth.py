"""Resolving and requiring the current signed-in person, plus PIN lockout.

Sign-in is by name + numeric PIN (see :mod:`chores.views`). The signed-in
person's id lives in ``request.session["person_id"]``; this module turns that
back into a :class:`~chores.models.Person` and gates views that need one.

It also owns the #14 PIN brute-force protection: :func:`login_is_locked`,
:func:`record_login_failure`, :func:`clear_login_failures` and the timing
equaliser :func:`run_dummy_pin_check`. The ``chores:login`` view calls them; the
store of record is :class:`~chores.models.PinLockout`.
"""

import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from chores.models import Person, PinLockout

logger = logging.getLogger("chores.auth")

# A real (throwaway) password hash so the locked-out code path can spend one
# ``check_password`` of equivalent cost to the normal path -- response latency
# must not reveal "locked" vs "wrong PIN".
_TIMING_HASH = make_password("pin-lockout-timing-equaliser")


def get_current_person(request):
    """Return the signed-in :class:`Person` for ``request`` or ``None``.

    Reads ``request.session["person_id"]``. Returns ``None`` (never raises)
    when the key is missing or points at a person that no longer exists. The
    result is cached on ``request._current_person`` so repeated calls in one
    request hit the database at most once.
    """
    cached = getattr(request, "_current_person", False)
    if cached is not False:
        return cached

    person_id = request.session.get("person_id")
    person = None
    if person_id is not None:
        person = Person.objects.filter(pk=person_id).first()

    request._current_person = person
    return person


def require_person(view_func):
    """Redirect to the sign-in page when there is no current person.

    On an unauthenticated request returns a 302 to
    ``chores:login?next=<current full path>``; otherwise calls ``view_func``
    unchanged.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if get_current_person(request) is None:
            login_url = reverse("chores:login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)

    return _wrapped


# --- PIN brute-force protection (#14) ---------------------------------------


def run_dummy_pin_check():
    """Spend one password-hash comparison, discarding the result.

    Called on the locked-out path so its latency matches the wrong-PIN path.
    """
    check_password("0000", _TIMING_HASH)


def _window_start():
    return timezone.now() - timedelta(seconds=settings.PIN_LOCKOUT_WINDOW)


def _lock_rows(person, ip):
    """Rows that can lock this attempt: the per-IP ceiling row and, if the
    person is known, the ``(person, ip)`` pair row."""
    q = Q(person=None, ip_address=ip)
    if person is not None:
        q |= Q(person=person, ip_address=ip)
    return PinLockout.objects.filter(q)


def login_is_locked(person, ip):
    """True when sign-in for ``(person, ip)`` is inside a cooldown right now.

    ``person`` may be ``None`` (missing/unknown ``person_id``); only the per-IP
    ceiling row is consulted then. The lock clears itself the moment
    ``timezone.now() >= locked_until`` -- no admin action required.
    """
    now = timezone.now()
    for row in _lock_rows(person, ip):
        if row.locked_until is not None and row.locked_until > now:
            return True
    return False


def _bump(person, ip, threshold):
    """Record one failure against the ``(person, ip)`` row and return
    ``(row, newly_locked)``. ``threshold`` of 0 disables locking for this row."""
    now = timezone.now()
    window = timedelta(seconds=settings.PIN_LOCKOUT_WINDOW)
    row, created = PinLockout.objects.get_or_create(
        person=person,
        ip_address=ip,
        defaults={
            "failure_count": 0,
            "first_failure_at": now,
            "last_failure_at": now,
        },
    )
    # Failures older than the rolling window don't count -- start fresh.
    if not created and row.last_failure_at < now - window:
        row.failure_count = 0
        row.locked_until = None

    if row.failure_count == 0:
        row.first_failure_at = now
    row.failure_count += 1
    row.last_failure_at = now

    newly_locked = False
    if threshold and row.failure_count >= threshold and row.locked_until is None:
        row.locked_until = now + window
        newly_locked = True

    row.save()
    return row, newly_locked


def record_login_failure(person, ip):
    """Count one failed ``POST chores:login`` and engage a lockout if due.

    Updates the ``(person, ip)`` pair row (when ``person`` is known) and always
    the per-IP ceiling row. A caller must not invoke this while the attempt is
    already locked (the view refuses first), so a locked pair/IP never has its
    ``failure_count`` bumped or its ``locked_until`` pushed further out.
    """
    pair = None
    if person is not None:
        pair = _bump(person, ip, settings.PIN_LOCKOUT_THRESHOLD)
    ceiling = _bump(None, ip, settings.PIN_LOCKOUT_IP_THRESHOLD)

    primary_row = (pair or ceiling)[0]
    logger.warning(
        "PIN login failure person=%s ip=%s failure_count=%s",
        person.id if person is not None else "-",
        ip,
        primary_row.failure_count,
    )

    if pair is not None and pair[1]:
        logger.warning(
            "PIN lockout engaged key=(person=%s, ip=%s) locked_until=%s",
            person.id,
            ip,
            pair[0].locked_until,
        )
    if ceiling[1]:
        logger.warning(
            "PIN lockout engaged key=(ip=%s, all persons) locked_until=%s",
            ip,
            ceiling[0].locked_until,
        )


def clear_login_failures(person, ip):
    """Wipe the failure count for ``(person, ip)`` after a successful sign-in.

    Deletes the pair row and relieves pressure on the per-IP ceiling row
    (decrement, or delete when it would hit zero).
    """
    if person is not None:
        PinLockout.objects.filter(person=person, ip_address=ip).delete()

    ceiling = PinLockout.objects.filter(person=None, ip_address=ip).first()
    if ceiling is None:
        return
    if ceiling.failure_count <= 1:
        ceiling.delete()
    else:
        ceiling.failure_count -= 1
        ceiling.locked_until = None
        ceiling.save(update_fields=["failure_count", "locked_until"])
