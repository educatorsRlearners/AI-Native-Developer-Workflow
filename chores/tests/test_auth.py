import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse

from chores.auth import get_current_person
from chores.models import Person

pytestmark = pytest.mark.django_db

PIN = "1357"


def make_person(name="Alex", email=None, pin=PIN):
    person = Person.objects.create(
        name=name, email=email or f"{name.lower()}@example.com", pin_hash="!"
    )
    if pin is not None:
        person.set_pin(pin)
        person.save(update_fields=["pin_hash"])
    return person


def sign_in(client, person):
    session = client.session
    session["person_id"] = person.id
    session.save()


# --- set_pin management command -------------------------------------------------


def _fake_getpass(values):
    it = iter(values)
    return lambda prompt="": next(it)


def test_set_pin_then_login(client, monkeypatch):
    person = make_person(pin=None)  # seeded "!" hash
    monkeypatch.setattr(
        "chores.management.commands.set_pin.getpass", _fake_getpass(["2468", "2468"])
    )
    call_command("set_pin", person.email)

    resp = client.post(
        reverse("chores:login"), {"person_id": person.id, "pin": "2468"}
    )
    assert resp.status_code == 302
    assert client.session["person_id"] == person.id


def test_set_pin_mismatch_writes_nothing(monkeypatch):
    person = make_person(pin=None)
    monkeypatch.setattr(
        "chores.management.commands.set_pin.getpass", _fake_getpass(["1111", "2222"])
    )
    with pytest.raises(CommandError):
        call_command("set_pin", person.email)
    person.refresh_from_db()
    assert person.pin_hash == "!"


def test_set_pin_unknown_email(monkeypatch):
    monkeypatch.setattr(
        "chores.management.commands.set_pin.getpass", _fake_getpass(["1111", "1111"])
    )
    with pytest.raises(CommandError):
        call_command("set_pin", "nobody@example.com")


def test_set_pin_never_echoes_raw_pin(capsys, monkeypatch):
    person = make_person(pin=None)
    monkeypatch.setattr(
        "chores.management.commands.set_pin.getpass", _fake_getpass(["9999", "9999"])
    )
    call_command("set_pin", person.email)
    captured = capsys.readouterr()
    assert "9999" not in captured.out
    assert "9999" not in captured.err
    assert "PIN set for" in captured.out


# --- gating -------------------------------------------------------------------


def test_unauthenticated_list_redirects_to_login(client):
    resp = client.get(reverse("chores:list"))
    assert resp.status_code == 302
    assert resp["Location"] == f"{reverse('chores:login')}?next=/"


def test_signed_in_list_ok_and_shows_name_and_signout(client):
    person = make_person("Robin")
    sign_in(client, person)
    resp = client.get(reverse("chores:list"))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "Robin" in body
    assert reverse("chores:logout") in body
    assert "Sign out" in body


# --- login -------------------------------------------------------------------


def test_login_get_renders_form(client):
    make_person()
    resp = client.get(reverse("chores:login"))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert 'method="post"' in body
    assert "csrfmiddlewaretoken" in body
    assert 'type="password"' in body
    assert 'inputmode="numeric"' in body


def test_login_correct_redirects_to_list(client):
    person = make_person()
    resp = client.post(
        reverse("chores:login"), {"person_id": person.id, "pin": PIN}
    )
    assert resp.status_code == 302
    assert resp["Location"] == reverse("chores:list")
    assert client.session["person_id"] == person.id


def test_login_safe_and_unsafe_next(client):
    person = make_person()
    safe = client.post(
        reverse("chores:login"),
        {"person_id": person.id, "pin": PIN, "next": "/somewhere/"},
    )
    assert safe["Location"] == "/somewhere/"

    person2 = make_person("Sam")
    evil = client.post(
        reverse("chores:login"),
        {"person_id": person2.id, "pin": PIN, "next": "https://evil.example/"},
    )
    assert evil["Location"] == reverse("chores:list")


def test_login_wrong_pin_and_no_pin_have_identical_body(client):
    # Same person, same submitted pin. Once with a real PIN set (wrong guess),
    # once still on the seeded "!" hash. The two response bodies must be equal.
    person = make_person("Alex", pin=None)  # "!" hash

    unset = client.post(
        reverse("chores:login"), {"person_id": person.id, "pin": "0000"}
    )
    assert unset.status_code == 200
    assert "match, try again" in unset.content.decode()
    assert "person_id" not in client.session

    person.set_pin("1357")
    person.save(update_fields=["pin_hash"])
    wrong = client.post(
        reverse("chores:login"), {"person_id": person.id, "pin": "0000"}
    )
    assert wrong.status_code == 200
    assert "person_id" not in client.session

    # NOTE: the form carries a per-request-masked {% csrf_token %}, so the
    # responses can never be *byte*-for-byte identical. Everything else must be.
    # (Raised as a comment on issue #7.)
    def strip_csrf(content):
        import re

        return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", content)

    assert strip_csrf(unset.content) == strip_csrf(wrong.content)


def test_login_wrong_pin_keeps_person_selected_blank_pin(client):
    person = make_person("Robin")
    resp = client.post(
        reverse("chores:login"), {"person_id": person.id, "pin": "0000"}
    )
    body = resp.content.decode()
    assert f'value="{person.id}"' in body
    assert "selected" in body
    assert 'name="pin" id="pin" value=""' in body


def test_login_unknown_person_id(client):
    resp = client.post(
        reverse("chores:login"), {"person_id": 999999, "pin": "0000"}
    )
    assert resp.status_code == 200
    assert "person_id" not in client.session


def test_already_signed_in_get_login_redirects(client):
    person = make_person()
    sign_in(client, person)
    resp = client.get(reverse("chores:login"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("chores:list")


def test_post_login_while_signed_in_replaces_person(client):
    a = make_person("Alex")
    b = make_person("Sam")
    sign_in(client, a)
    client.post(reverse("chores:login"), {"person_id": b.id, "pin": PIN})
    assert client.session["person_id"] == b.id


# --- logout ------------------------------------------------------------------


def test_logout_post_redirects_and_clears(client):
    person = make_person()
    sign_in(client, person)
    resp = client.post(reverse("chores:logout"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("chores:login")
    assert "person_id" not in client.session


def test_logout_get_405(client):
    resp = client.get(reverse("chores:logout"))
    assert resp.status_code == 405


# --- get_current_person ------------------------------------------------------


def test_get_current_person_none_when_deleted(client, rf):
    person = make_person()
    request = rf.get("/")
    request.session = {"person_id": person.id}
    assert get_current_person(request).id == person.id

    person.delete()
    request2 = rf.get("/")
    request2.session = {"person_id": person.id}
    assert get_current_person(request2) is None


def test_get_current_person_caches(rf, django_assert_num_queries):
    person = make_person()
    request = rf.get("/")
    request.session = {"person_id": person.id}
    with django_assert_num_queries(1):
        get_current_person(request)
        get_current_person(request)


def test_get_current_person_missing_key(rf):
    request = rf.get("/")
    request.session = {}
    assert get_current_person(request) is None


# --- CSRF ------------------------------------------------------------------


def test_login_post_without_csrf_token_403():
    csrf_client = Client(enforce_csrf_checks=True)
    person = make_person()
    resp = csrf_client.post(
        reverse("chores:login"), {"person_id": person.id, "pin": PIN}
    )
    assert resp.status_code == 403
    assert "person_id" not in csrf_client.session


def test_logout_post_without_csrf_token_403():
    csrf_client = Client(enforce_csrf_checks=True)
    person = make_person()
    session = csrf_client.session
    session["person_id"] = person.id
    session.save()
    resp = csrf_client.post(reverse("chores:logout"))
    assert resp.status_code == 403
    assert csrf_client.session["person_id"] == person.id
