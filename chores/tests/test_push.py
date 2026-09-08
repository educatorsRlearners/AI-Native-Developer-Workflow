import json

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from chores.models import Person, PushSubscription

pytestmark = pytest.mark.django_db

VAPID_PUBLIC = "BJ_test_public_key_base64url"
VAPID_PRIVATE = "test_private_key_never_rendered"


def make_person(name="Alex", email=None):
    return Person.objects.create(
        name=name, email=email or f"{name.lower()}@example.com", pin_hash="!"
    )


def sign_in(client, person):
    session = client.session
    session["person_id"] = person.id
    session.save()


def body(endpoint="https://push.example.com/sub/abc", p256dh="key-p", auth="key-a"):
    return json.dumps(
        {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
    )


def post_sub(client, payload):
    return client.post(
        reverse("chores:push-subscribe"),
        data=payload,
        content_type="application/json",
    )


# --- subscribe endpoint -----------------------------------------------------


def test_subscribe_creates_one_row(client):
    person = make_person()
    sign_in(client, person)

    resp = post_sub(client, body())

    assert resp.status_code == 201
    assert json.loads(resp.content) == {"status": "created"}
    subs = PushSubscription.objects.all()
    assert subs.count() == 1
    sub = subs.get()
    assert sub.person == person
    assert sub.endpoint == "https://push.example.com/sub/abc"
    assert sub.p256dh == "key-p"
    assert sub.auth == "key-a"


def test_resubscribe_same_endpoint_updates_in_place(client):
    person = make_person()
    sign_in(client, person)
    post_sub(client, body())

    resp = post_sub(client, body(p256dh="key-p2", auth="key-a2"))

    assert resp.status_code == 200
    assert json.loads(resp.content) == {"status": "updated"}
    assert PushSubscription.objects.count() == 1
    sub = PushSubscription.objects.get()
    assert sub.p256dh == "key-p2"
    assert sub.auth == "key-a2"


def test_resubscribe_as_different_person_repoints_row(client):
    alex = make_person("Alex")
    sam = make_person("Sam")
    sign_in(client, alex)
    post_sub(client, body())

    other = Client()
    sign_in(other, sam)
    resp = post_sub(other, body())

    assert resp.status_code == 200
    assert PushSubscription.objects.count() == 1
    assert PushSubscription.objects.get().person == sam


def test_subscribe_signed_out_redirects_and_saves_nothing(client):
    resp = post_sub(client, body())
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert reverse("chores:login") in resp["Location"]
    assert PushSubscription.objects.count() == 0


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        json.dumps({"keys": {"p256dh": "p", "auth": "a"}}),  # no endpoint
        json.dumps({"endpoint": "https://x/y", "keys": {"p256dh": "p"}}),  # no auth
        json.dumps({"endpoint": "https://x/y"}),  # no keys
        json.dumps(["a", "list"]),
    ],
)
def test_subscribe_malformed_body_400_saves_nothing(client, payload):
    sign_in(client, make_person())
    resp = post_sub(client, payload)
    assert resp.status_code == 400
    assert "error" in json.loads(resp.content)
    assert PushSubscription.objects.count() == 0


def test_subscribe_get_405(client):
    sign_in(client, make_person())
    resp = client.get(reverse("chores:push-subscribe"))
    assert resp.status_code == 405


def test_subscribe_csrf_protected(client):
    csrf_client = Client(enforce_csrf_checks=True)
    sign_in(csrf_client, make_person())
    resp = csrf_client.post(
        reverse("chores:push-subscribe"),
        data=body(),
        content_type="application/json",
    )
    assert resp.status_code == 403
    assert PushSubscription.objects.count() == 0


# --- settings page --------------------------------------------------------


@override_settings(VAPID_PUBLIC_KEY=VAPID_PUBLIC, VAPID_PRIVATE_KEY=VAPID_PRIVATE)
def test_settings_page_signed_in(client):
    sign_in(client, make_person("Robin"))
    resp = client.get(reverse("chores:settings"))
    assert resp.status_code == 200
    text = resp.content.decode()
    assert "<html" in text
    assert "Enable notifications" in text
    assert "id=\"enable-notifications\"" in text
    assert VAPID_PUBLIC in text
    assert VAPID_PRIVATE not in text
    assert "chores/push.js" in text


def test_settings_page_signed_out_redirects_to_login(client):
    resp = client.get(reverse("chores:settings"))
    assert resp.status_code == 302
    assert resp["Location"] == f"{reverse('chores:login')}?next={reverse('chores:settings')}"


# --- service worker ------------------------------------------------------


def test_sw_has_push_and_notificationclick_listeners(client):
    body_text = client.get("/sw.js").content.decode()
    assert 'addEventListener("push"' in body_text
    assert 'addEventListener("notificationclick"' in body_text
    assert "showNotification" in body_text
    assert "matchAll" in body_text
    assert "includeUncontrolled" in body_text
    assert "openWindow" in body_text
    # #8 caching behaviour untouched
    assert "CACHE_VERSION" in body_text
    assert 'addEventListener("fetch"' in body_text


# --- model -------------------------------------------------------------------


def test_str_has_person_and_host_not_key_material(client):
    person = make_person("Dana")
    sub = PushSubscription.objects.create(
        person=person,
        endpoint="https://fcm.googleapis.com/fcm/send/xyz",
        p256dh="secret-p256dh-material",
        auth="secret-auth-material",
    )
    label = str(sub)
    assert "Dana" in label
    assert "fcm.googleapis.com" in label
    assert "secret-p256dh-material" not in label
    assert "secret-auth-material" not in label
