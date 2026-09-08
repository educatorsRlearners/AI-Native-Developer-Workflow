"""Tests for chores.recurrence -- pure functions, standard library only."""

import datetime
import inspect
import subprocess
import sys

import pytest

from chores import recurrence
from chores.recurrence import is_overdue, next_due

D = datetime.date


def DT(*args):
    return datetime.datetime(*args, tzinfo=datetime.UTC)


def test_no_django_in_sys_modules_after_fresh_import():
    code = (
        "import sys; import chores.recurrence; "
        "assert 'django' not in sys.modules, sorted(sys.modules); "
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_module_reads_no_clock():
    source = inspect.getsource(recurrence)
    assert "today(" not in source
    assert "now(" not in source
    assert "utcnow(" not in source


# --- last_completed is None -> anchor_date for every cadence ---


@pytest.mark.parametrize("cadence", ["DAILY", "WEEKLY", "MONTHLY", "CUSTOM"])
def test_first_occurrence_returns_anchor_date(cadence):
    anchor = D(2026, 3, 4)
    kwargs = {"custom_interval_days": 3} if cadence == "CUSTOM" else {}
    assert next_due(cadence, anchor, None, **kwargs) == anchor


# --- DAILY / WEEKLY ---


def test_daily_adds_one_day():
    assert next_due("DAILY", D(2000, 1, 1), D(2026, 1, 20)) == D(2026, 1, 21)


def test_weekly_adds_seven_days():
    assert next_due("WEEKLY", D(2000, 1, 1), D(2026, 1, 20)) == D(2026, 1, 27)


def test_daily_ignores_anchor_date():
    a = next_due("DAILY", D(1999, 7, 7), D(2026, 1, 20))
    b = next_due("DAILY", D(2050, 12, 31), D(2026, 1, 20))
    assert a == b == D(2026, 1, 21)


def test_weekly_ignores_anchor_date():
    a = next_due("WEEKLY", D(1999, 7, 7), D(2026, 1, 20))
    b = next_due("WEEKLY", D(2050, 12, 31), D(2026, 1, 20))
    assert a == b == D(2026, 1, 27)


# --- MONTHLY rows from the issue ---


@pytest.mark.parametrize(
    ("anchor_day", "last_completed", "expected"),
    [
        (15, D(2026, 1, 20), D(2026, 2, 15)),
        (31, D(2026, 1, 10), D(2026, 2, 28)),
        (31, D(2028, 1, 10), D(2028, 2, 29)),
        (31, D(2026, 3, 10), D(2026, 4, 30)),
        (29, D(2026, 1, 5), D(2026, 2, 28)),
        (30, D(2028, 1, 5), D(2028, 2, 29)),
        (10, D(2026, 12, 4), D(2027, 1, 10)),
    ],
)
def test_monthly_rows(anchor_day, last_completed, expected):
    anchor = D(2020, 1, anchor_day)
    assert next_due("MONTHLY", anchor, last_completed) == expected


def test_monthly_day_comes_from_anchor_not_last_completed():
    assert next_due("MONTHLY", D(2020, 1, 3), D(2026, 1, 27)) == D(2026, 2, 3)


# --- CUSTOM ---


def test_custom_adds_interval():
    assert next_due("CUSTOM", D(2000, 1, 1), D(2026, 1, 20), 10) == D(2026, 1, 30)


@pytest.mark.parametrize("bad", [None, 0, -5])
def test_custom_rejects_bad_interval(bad):
    with pytest.raises(ValueError, match="custom_interval_days"):
        next_due("CUSTOM", D(2026, 1, 1), D(2026, 1, 20), bad)


def test_custom_none_interval_rejected_even_when_last_completed_is_none():
    with pytest.raises(ValueError, match="custom_interval_days"):
        next_due("CUSTOM", D(2026, 1, 1), None, None)


def test_custom_interval_ignored_for_non_custom_cadence():
    assert next_due("DAILY", D(2000, 1, 1), D(2026, 1, 20), 999) == D(2026, 1, 21)


# --- unknown cadence ---


@pytest.mark.parametrize("bad", ["", "daily", "Daily", None, "YEARLY"])
def test_unknown_cadence_raises_with_value(bad):
    with pytest.raises(ValueError, match=repr(bad)):
        next_due(bad, D(2026, 1, 1), D(2026, 1, 20))


# --- is_overdue boundary ---


def test_is_overdue_on_due_date_is_false():
    assert is_overdue(D(2026, 1, 20), D(2026, 1, 20)) is False


def test_is_overdue_day_before_is_false():
    assert is_overdue(D(2026, 1, 20), D(2026, 1, 19)) is False


def test_is_overdue_day_after_is_true():
    assert is_overdue(D(2026, 1, 20), D(2026, 1, 21)) is True


# --- datetime rejection ---


def test_next_due_rejects_datetime_anchor():
    with pytest.raises(TypeError):
        next_due("DAILY", DT(2026, 1, 1), D(2026, 1, 20))


def test_next_due_rejects_datetime_last_completed():
    with pytest.raises(TypeError):
        next_due("DAILY", D(2026, 1, 1), DT(2026, 1, 20))


def test_is_overdue_rejects_datetime():
    with pytest.raises(TypeError):
        is_overdue(DT(2026, 1, 20), D(2026, 1, 21))
    with pytest.raises(TypeError):
        is_overdue(D(2026, 1, 20), DT(2026, 1, 21))


def test_arguments_not_mutated():
    anchor = D(2020, 6, 15)
    last = D(2026, 1, 20)
    next_due("MONTHLY", anchor, last)
    assert anchor == D(2020, 6, 15)
    assert last == D(2026, 1, 20)
