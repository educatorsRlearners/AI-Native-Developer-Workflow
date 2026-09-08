import datetime

import pytest
from django.utils import timezone

from chores import recurrence
from chores.models import Chore, Completion, Person
from chores.services import (
    ChoreClaimError,
    claim_chore,
    complete_chore,
    last_completed_on,
)

pytestmark = pytest.mark.django_db


def make_person(name="Pat", email="pat@example.com"):
    return Person.objects.create(name=name, email=email, pin_hash="!")


def make_chore(owner=None, cadence=Chore.Cadence.DAILY, **kwargs):
    defaults = {
        "title": "Dishes",
        "cadence": cadence,
        "anchor_date": datetime.date(2026, 1, 1),
        "owner": owner,
    }
    defaults.update(kwargs)
    return Chore.objects.create(**defaults)


def test_complete_with_explicit_when():
    person = make_person()
    chore = make_chore()
    when = timezone.now() - datetime.timedelta(days=2)

    c = complete_chore(chore, person, when=when)

    assert Completion.objects.filter(chore=chore).count() == 1
    assert c.person == person
    assert c.completed_at == when


def test_complete_without_when_uses_now():
    person = make_person()
    chore = make_chore()

    c = complete_chore(chore, person)

    assert abs((timezone.now() - c.completed_at).total_seconds()) < 5


def test_completing_daily_chore_moves_next_due_forward_one_day():
    person = make_person()
    chore = make_chore(cadence=Chore.Cadence.DAILY)
    when = timezone.now()

    complete_chore(chore, person, when=when)

    last = last_completed_on(chore)
    due = recurrence.next_due(
        chore.cadence, chore.anchor_date, last, chore.custom_interval_days
    )
    assert due == last + datetime.timedelta(days=1)


def test_completion_clears_outstanding_claim():
    person = make_person()
    other = make_person(name="Sam", email="sam@example.com")
    chore = make_chore()
    claim_chore(chore, other)

    complete_chore(chore, person)

    chore.refresh_from_db()
    assert chore.claimed_by is None
    assert chore.claimed_at is None


def test_completion_on_unclaimed_chore_succeeds():
    person = make_person()
    chore = make_chore()

    complete_chore(chore, person)

    chore.refresh_from_db()
    assert chore.claimed_by is None
    assert chore.claimed_at is None
    assert Completion.objects.filter(chore=chore).count() == 1


def test_complete_twice_writes_two_rows():
    person = make_person()
    chore = make_chore()

    complete_chore(chore, person)
    complete_chore(chore, person)

    assert Completion.objects.filter(chore=chore).count() == 2


def test_complete_with_naive_when_raises_value_error():
    person = make_person()
    chore = make_chore()
    naive = timezone.now().replace(tzinfo=None)

    with pytest.raises(ValueError, match="when"):
        complete_chore(chore, person, when=naive)

    assert Completion.objects.filter(chore=chore).count() == 0


def test_last_completed_on_none_without_completions():
    chore = make_chore()
    assert last_completed_on(chore) is None


def test_past_completion_does_not_win_over_later_one():
    person = make_person()
    chore = make_chore()
    later = timezone.now()
    earlier = later - datetime.timedelta(days=10)

    complete_chore(chore, person, when=later)
    complete_chore(chore, person, when=earlier)

    assert last_completed_on(chore) == timezone.localtime(later).date()


def test_claim_pooled_chore_sets_claimed_by():
    person = make_person()
    chore = make_chore(owner=None)

    result = claim_chore(chore, person)

    assert result.claimed_by == person
    assert result.claimed_at is not None


def test_claim_owned_chore_raises_and_leaves_unchanged():
    owner = make_person(name="Owner", email="owner@example.com")
    claimer = make_person(name="Claimer", email="claimer@example.com")
    chore = make_chore(owner=owner)

    with pytest.raises(ValueError, match="Dishes"):
        claim_chore(chore, claimer)

    chore.refresh_from_db()
    assert chore.claimed_by is None
    assert chore.claimed_at is None


def test_chore_claim_error_is_value_error():
    assert issubclass(ChoreClaimError, ValueError)


def test_reclaim_reassigns_and_moves_claimed_at_forward():
    a = make_person(name="A", email="a@example.com")
    b = make_person(name="B", email="b@example.com")
    chore = make_chore(owner=None)

    first = claim_chore(chore, a)
    first_at = first.claimed_at
    second = claim_chore(chore, b)

    assert second.claimed_by == b
    assert second.claimed_at >= first_at


def test_claim_does_not_create_completion():
    person = make_person()
    chore = make_chore(owner=None)

    claim_chore(chore, person)

    assert Completion.objects.filter(chore=chore).count() == 0
