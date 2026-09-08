import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from chores.models import Chore, Completion, Person

pytestmark = pytest.mark.django_db


def make_person(name, email=None):
    return Person.objects.create(
        name=name, email=email or f"{name.lower()}@example.com", pin_hash="!"
    )


def make_chore(title, owner=None, cadence=Chore.Cadence.DAILY, **kwargs):
    defaults = {
        "title": title,
        "cadence": cadence,
        "anchor_date": timezone.localdate(),
        "owner": owner,
    }
    defaults.update(kwargs)
    return Chore.objects.create(**defaults)


def test_list_page_renders_groups_and_activity(client):
    alice = make_person("Alice")
    make_person("Bob")

    owned = make_chore("Wash dishes", owner=alice)
    make_chore("Take out trash", owner=None)

    overdue = make_chore(
        "Vacuum", owner=alice, anchor_date=timezone.localdate() - datetime.timedelta(days=3)
    )

    Completion.objects.create(
        chore=owned, person=alice, completed_at=timezone.now() - datetime.timedelta(hours=1)
    )

    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "Wash dishes" in body
    assert "Take out trash" in body
    assert "Alice" in body
    assert "Pool" in body
    assert "Overdue" in body
    assert overdue.title in body
    # activity
    assert "Wash dishes" in body
    assert "Alice" in body


def test_empty_states(client):
    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "No chores yet" in body
    assert "Nothing done yet" in body


def test_independent_empty_states(client):
    alice = make_person("Alice")
    make_chore("Wash dishes", owner=alice)

    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()
    assert "No chores yet" not in body
    assert "Nothing done yet" in body


def test_due_today_marker(client):
    alice = make_person("Alice")
    # never completed, anchor today -> next_due == today
    make_chore("Water plants", owner=alice, anchor_date=timezone.localdate())

    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()
    assert "Due today" in body
    assert "Overdue" not in body


def test_no_interactivity(client):
    alice = make_person("Alice")
    chore = make_chore("Wash dishes", owner=alice)
    Completion.objects.create(chore=chore, person=alice)

    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()
    assert "<form" not in body
    assert "<button" not in body
    assert "<script" not in body


def test_never_completed_shows_never(client):
    alice = make_person("Alice")
    make_chore("Wash dishes", owner=alice)

    resp = client.get(reverse("chores:list"))
    assert "Never" in resp.content.decode()


def test_claimed_pooled_chore_shows_claimer(client):
    bob = make_person("Bob")
    make_chore(
        "Take out trash",
        owner=None,
        claimed_by=bob,
        claimed_at=timezone.now(),
    )

    resp = client.get(reverse("chores:list"))
    assert "Claimed by Bob" in resp.content.decode()


def test_empty_group_not_rendered(client):
    make_person("Zoe")  # owns nothing
    alice = make_person("Alice")
    make_chore("Wash dishes", owner=alice)

    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()
    assert "Alice" in body
    assert "Zoe" not in body
    assert "Pool" not in body


def test_activity_capped_at_ten(client):
    alice = make_person("Alice")
    chore = make_chore("Wash dishes", owner=alice)
    for i in range(12):
        Completion.objects.create(
            chore=chore,
            person=alice,
            completed_at=timezone.now() - datetime.timedelta(minutes=i),
        )

    resp = client.get(reverse("chores:list"))
    assert resp.content.decode().count('class="activity-row"') == 10
