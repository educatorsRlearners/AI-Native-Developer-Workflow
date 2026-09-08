"""Pure recurrence math for chores.

Standard library only. No Django, no models, no database, no I/O, and no clock
reads: every "current date" is passed in as ``as_of``. Same inputs always produce
the same outputs, and argument objects are never mutated.

All date parameters and return values are :class:`datetime.date`. A
:class:`datetime.datetime` is rejected with :class:`TypeError` (``datetime`` is a
subclass of ``date`` and would otherwise slip through the checks). Callers that
hold a ``datetime`` must convert it with ``.date()`` themselves; this module does
not do it for them.

Cadence strings are kept identical to ``Chore.Cadence`` in ``chores/models.py``:
``"DAILY"``, ``"WEEKLY"``, ``"MONTHLY"``, ``"CUSTOM"``.
"""

import calendar
import datetime

DAILY = "DAILY"
WEEKLY = "WEEKLY"
MONTHLY = "MONTHLY"
CUSTOM = "CUSTOM"

_CADENCES = (DAILY, WEEKLY, MONTHLY, CUSTOM)


def _require_date(value, name):
    """Return ``value`` if it is a plain ``date``; otherwise raise ``TypeError``.

    A ``datetime`` instance is rejected explicitly even though it is a subclass
    of ``date``.
    """
    if isinstance(value, datetime.datetime):
        raise TypeError(
            f"{name} must be a datetime.date, not datetime.datetime; "
            "convert it with .date() first"
        )
    if not isinstance(value, datetime.date):
        raise TypeError(f"{name} must be a datetime.date, got {type(value).__name__}")
    return value


def next_due(cadence, anchor_date, last_completed, custom_interval_days=None):
    """Return the next due :class:`datetime.date`, one period after completion.

    Advances exactly one period from ``last_completed``. It does not roll forward
    over several missed periods.

    Parameters
    ----------
    cadence:
        One of ``"DAILY"``, ``"WEEKLY"``, ``"MONTHLY"``, ``"CUSTOM"`` (exact
        match, case-sensitive). Any other value raises :class:`ValueError` naming
        the offending value.
    anchor_date:
        The chore's anchor date (a ``date``). Used as the first occurrence when
        ``last_completed is None``, and, for ``MONTHLY``, supplies the
        day-of-month. Ignored by ``DAILY`` and ``WEEKLY`` once ``last_completed``
        is set.
    last_completed:
        The date the chore was last completed (a ``date``), or ``None`` for the
        first occurrence.
    custom_interval_days:
        Required (integer >= 1) only when ``cadence == "CUSTOM"``. Passing it
        alongside any other cadence is ignored and does not raise.

    Raises
    ------
    ValueError
        If ``cadence`` is not one of the four strings, or if ``cadence`` is
        ``"CUSTOM"`` and ``custom_interval_days`` is ``None``, ``0``, or less
        than ``1`` (the message names ``custom_interval_days``).
    TypeError
        If any date argument is a ``datetime.datetime`` or not a ``date`` at all.
    """
    if cadence not in _CADENCES:
        raise ValueError(f"Unknown cadence: {cadence!r}")

    _require_date(anchor_date, "anchor_date")
    if last_completed is not None:
        _require_date(last_completed, "last_completed")

    if cadence == CUSTOM and (
        custom_interval_days is None or custom_interval_days < 1
    ):
        raise ValueError(
            "custom_interval_days must be an integer >= 1 when cadence is "
            f"CUSTOM, got {custom_interval_days!r}"
        )

    if last_completed is None:
        return anchor_date

    if cadence == DAILY:
        return last_completed + datetime.timedelta(days=1)
    if cadence == WEEKLY:
        return last_completed + datetime.timedelta(days=7)
    if cadence == CUSTOM:
        return last_completed + datetime.timedelta(days=custom_interval_days)

    # MONTHLY: the calendar month after last_completed's month, on
    # anchor_date.day, clamped to that month's last day.
    year = last_completed.year
    month = last_completed.month + 1
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(anchor_date.day, last_day)
    return datetime.date(year, month, day)


def is_overdue(due_date, as_of):
    """Return ``True`` when ``as_of`` is strictly after ``due_date``.

    The boundary: ``as_of > due_date`` is overdue. On the due date itself the
    chore is not overdue, and it is not overdue on any earlier date.

    Both arguments must be :class:`datetime.date`; a ``datetime.datetime`` raises
    :class:`TypeError`.
    """
    _require_date(due_date, "due_date")
    _require_date(as_of, "as_of")
    return as_of > due_date
