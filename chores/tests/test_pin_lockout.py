"""PIN brute-force protection (#14).

Time is advanced by monkeypatching ``django.utils.timezone.now`` -- both
``chores.auth`` and the model default call ``timezone.now()`` through that
module, so one patch moves the whole clock.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from chores.models import Person, PinLockout

pytestmark = pytest.mark.django_db

PIN = "1357"
WRONG = "0000"
LOGIN = "chores:login"


def make_person(name="Alex", pin=PIN):
    person = Person.objects.create(
        name=name, email=f"{name.lower()}@example.com", pin_hash="!"
    )
    if pin is not None:
        person.set_pin(pin)
        person.save(update_fields=["pin_hash"])
    return person


def freeze(monkeypatch, when):
    monkeypatch.setattr(timezone, "now", lambda: when)


def post(client, person_id, pin):
    return client.post(reverse(LOGIN), {"person_id": person_id, "pin": pin})


def strip_csrf(content):
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", content)


def test_below_threshold_then_correct_pin_signs_in(client, settings):
    person = make_person()
    for _ in range(settings.PIN_LOCKOUT_THRESHOLD - 1):
        assert post(client, person.id, WRONG).status_code == 200
    resp = post(client, person.id, PIN)
    assert resp.status_code == 302
    assert client.session["person_id"] == person.id


def test_threshold_reached_blocks_correct_pin(client, settings):
    person = make_person()
    for _ in range(settings.PIN_LOCKOUT_THRESHOLD):
        post(client, person.id, WRONG)
    resp = post(client, person.id, PIN)
    assert resp.status_code == 200
    assert "person_id" not in client.session
    body = resp.content.decode()
    assert "Too many attempts, try again later." in body
    assert "match, try again" in body  # the #7 wrong-PIN text, kept verbatim


def test_lock_clears_itself_after_window(client, settings, monkeypatch):
    start = timezone.now()
    freeze(monkeypatch, start)
    person = make_person()
    for _ in range(settings.PIN_LOCKOUT_THRESHOLD):
        post(client, person.id, WRONG)
    assert post(client, person.id, PIN).status_code == 200

    freeze(monkeypatch, start + timedelta(seconds=settings.PIN_LOCKOUT_WINDOW + 1))
    resp = post(client, person.id, PIN)
    assert resp.status_code == 302
    assert client.session["person_id"] == person.id
    assert not PinLockout.objects.filter(person=person).exists()


def test_success_midway_resets_count(client, settings):
    person = make_person()
    for _ in range(3):
        post(client, person.id, WRONG)
    assert post(client, person.id, PIN).status_code == 302
    assert not PinLockout.objects.filter(person=person).exists()

    client.post(reverse("chores:logout"))
    post(client, person.id, WRONG)
    row = PinLockout.objects.get(person=person)
    assert row.failure_count == 1


def test_no_pin_set_counts_and_locked_body_matches_wrong_pin(client, settings):
    # Same person: first locked while still on the seeded "!" hash (no PIN set),
    # then locked with a real PIN set (wrong guess). The two locked response
    # bodies must be identical (modulo the per-request csrf mask).
    person = make_person("Sam", pin=None)  # "!" hash
    for _ in range(settings.PIN_LOCKOUT_THRESHOLD):
        post(client, person.id, WRONG)
    assert (
        PinLockout.objects.get(person=person).failure_count
        >= settings.PIN_LOCKOUT_THRESHOLD
    )
    locked_nopin = post(client, person.id, "9999")

    person.set_pin(PIN)
    person.save(update_fields=["pin_hash"])
    locked_wrong = post(client, person.id, "9999")

    assert locked_nopin.status_code == locked_wrong.status_code == 200
    assert "Too many attempts, try again later." in locked_nopin.content.decode()
    assert strip_csrf(locked_nopin.content) == strip_csrf(locked_wrong.content)


def test_person_a_lock_does_not_lock_person_b_same_ip(client, settings):
    a = make_person("Aaa")
    b = make_person("Bbb")
    for _ in range(settings.PIN_LOCKOUT_THRESHOLD):
        post(client, a.id, WRONG)
    assert post(client, a.id, PIN).status_code == 200  # A locked
    assert post(client, b.id, PIN).status_code == 302  # B fine
    assert client.session["person_id"] == b.id


def test_ip_ceiling_locks_untried_person(client, settings, monkeypatch):
    settings.PIN_LOCKOUT_IP_THRESHOLD = 6
    settings.PIN_LOCKOUT_THRESHOLD = 100
    people = [make_person(f"P{i}") for i in range(6)]
    for person in people:
        post(client, person.id, WRONG)
    fresh = make_person("Fresh")
    resp = post(client, fresh.id, PIN)
    assert resp.status_code == 200
    assert "person_id" not in client.session


def test_post_while_locked_does_not_extend(client, settings):
    person = make_person()
    for _ in range(settings.PIN_LOCKOUT_THRESHOLD):
        post(client, person.id, WRONG)
    row = PinLockout.objects.get(person=person)
    count, until = row.failure_count, row.locked_until

    for _ in range(3):
        post(client, person.id, WRONG)
    row.refresh_from_db()
    assert row.failure_count == count
    assert row.locked_until == until


def test_threshold_zero_never_locks(client, settings, monkeypatch):
    settings.PIN_LOCKOUT_THRESHOLD = 0
    settings.PIN_LOCKOUT_IP_THRESHOLD = 0
    person = make_person()
    for _ in range(30):
        assert post(client, person.id, WRONG).status_code == 200
    assert post(client, person.id, PIN).status_code == 302


def test_unknown_person_tracked_under_ip_only(client, settings):
    post(client, 999999, WRONG)
    assert PinLockout.objects.filter(person=None).count() == 1
    assert PinLockout.objects.exclude(person=None).count() == 0


def test_failure_logs_warning_without_raw_pin(client, settings, caplog):
    person = make_person()
    with caplog.at_level("WARNING", logger="chores.auth"):
        post(client, person.id, "8642")
    msgs = [r.message for r in caplog.records]
    assert any("failure_count=1" in m for m in msgs)
    assert all("8642" not in m for m in msgs)


def test_lockout_engaged_logs_warning(client, settings, caplog):
    person = make_person()
    with caplog.at_level("WARNING", logger="chores.auth"):
        for _ in range(settings.PIN_LOCKOUT_THRESHOLD):
            post(client, person.id, WRONG)
    assert any("lockout engaged" in r.message.lower() for r in caplog.records)


def test_is_currently_locked_property():
    row = PinLockout(ip_address="1.2.3.4")
    assert row.is_currently_locked is False
    row.locked_until = timezone.now() + timedelta(seconds=60)
    assert row.is_currently_locked is True
