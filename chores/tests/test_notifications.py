import datetime

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import override_settings

from chores.models import Chore, Completion, Person
from chores.notifications import send_nag_email

pytestmark = pytest.mark.django_db


def make_person(name="Pat", email="pat@example.com"):
    return Person.objects.create(name=name, email=email, pin_hash="!")


def make_chore(title="Dishes", cadence=Chore.Cadence.DAILY, **kwargs):
    defaults = {
        "title": title,
        "cadence": cadence,
        "anchor_date": datetime.date(2026, 1, 1),
    }
    defaults.update(kwargs)
    return Chore.objects.create(**defaults)


def test_two_chores_single_digest():
    person = make_person()
    a = make_chore(title="Wash dishes")
    b = make_chore(title="Take out trash")
    Completion.objects.create(
        chore=a,
        person=person,
        completed_at=datetime.datetime(2026, 2, 1, 12, tzinfo=datetime.UTC),
    )

    send_nag_email(person, [a, b])

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [person.email]
    assert msg.from_email == "chores@localhost"
    assert not msg.cc
    assert not msg.bcc
    assert msg.subject == "2 chores need doing"
    html = msg.alternatives[0][0]
    assert msg.alternatives[0][1] == "text/html"
    for title in ("Wash dishes", "Take out trash"):
        assert title in msg.body
        assert title in html


def test_one_chore_subject_singular():
    person = make_person()
    chore = make_chore(title="Vacuum")

    send_nag_email(person, [chore])

    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "1 chore needs doing"


def test_empty_list_sends_nothing():
    person = make_person()

    send_nag_email(person, [])

    assert mail.outbox == []


def test_no_email_address_logs_warning(caplog):
    person = make_person(email="")
    chore = make_chore()

    with caplog.at_level("WARNING"):
        send_nag_email(person, [chore])

    assert mail.outbox == []
    assert any(
        r.levelname == "WARNING" and person.name in r.getMessage()
        for r in caplog.records
    )


def test_chore_with_no_completions_shows_anchor_date():
    person = make_person()
    chore = make_chore(title="Water plants", anchor_date=datetime.date(2026, 3, 15))

    send_nag_email(person, [chore])

    msg = mail.outbox[0]
    assert "2026-03-15" in msg.body
    assert "2026-03-15" in msg.alternatives[0][0]


@override_settings(
    EMAIL_BACKEND="chores.tests.test_notifications.FailingBackend"
)
def test_backend_error_propagates():
    person = make_person()
    chore = make_chore()

    with pytest.raises(RuntimeError, match="smtp is down"):
        send_nag_email(person, [chore])


class FailingBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise RuntimeError("smtp is down")
