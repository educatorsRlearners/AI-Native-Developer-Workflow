import pytest
from django.core.management import call_command

from chores.models import Person

pytestmark = pytest.mark.django_db


def test_seed_people_is_idempotent():
    call_command("seed_people")
    call_command("seed_people")
    assert Person.objects.count() == 2


def test_seed_people_does_not_overwrite_pin_hash():
    call_command("seed_people", "--person1-email", "keep@example.com",
                 "--person2-email", "other@example.com")
    person = Person.objects.get(email="keep@example.com")
    person.set_pin("4321")
    person.save()
    hashed = person.pin_hash

    call_command("seed_people", "--person1-email", "keep@example.com",
                 "--person2-email", "other@example.com")
    person.refresh_from_db()
    assert person.pin_hash == hashed
    assert Person.objects.count() == 2


def test_seed_people_leaves_unusable_pin():
    call_command("seed_people")
    for person in Person.objects.all():
        assert person.check_pin("0000") is False
