import datetime

import pytest
from django.core.exceptions import ValidationError

from chores.models import Chore, Person

pytestmark = pytest.mark.django_db


def make_person(email="p@example.com"):
    return Person.objects.create(name="Pat", email=email, pin_hash="!")


def base_chore(**kwargs):
    defaults = {
        "title": "Dishes",
        "cadence": Chore.Cadence.DAILY,
        "anchor_date": datetime.date(2026, 1, 1),
    }
    defaults.update(kwargs)
    return Chore(**defaults)


def test_owned_chore_is_not_pooled():
    person = make_person()
    chore = base_chore(owner=person)
    assert chore.is_pooled is False
    assert chore.owner == person


def test_pooled_chore_has_no_owner():
    chore = base_chore(owner=None)
    assert chore.owner is None
    assert chore.is_pooled is True


def test_custom_cadence_requires_interval():
    chore = base_chore(cadence=Chore.Cadence.CUSTOM)
    with pytest.raises(ValidationError):
        chore.full_clean()


def test_non_custom_cadence_rejects_interval():
    chore = base_chore(cadence=Chore.Cadence.WEEKLY, custom_interval_days=3)
    with pytest.raises(ValidationError):
        chore.full_clean()


def test_person_pin_round_trip():
    person = make_person()
    person.set_pin("1234")
    assert person.pin_hash != "1234"
    assert person.check_pin("1234") is True
    assert person.check_pin("0000") is False
