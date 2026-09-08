import json

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_manifest_served_at_root_with_type_and_valid_json(client):
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/manifest+json"

    data = json.loads(resp.content)
    for key in (
        "name",
        "short_name",
        "start_url",
        "scope",
        "display",
        "theme_color",
        "background_color",
        "description",
        "icons",
    ):
        assert data.get(key), f"missing/empty manifest key: {key}"

    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    assert data["display"] == "standalone"

    sizes = {i["sizes"] for i in data["icons"]}
    assert "192x192" in sizes
    assert "512x512" in sizes
    assert any("maskable" in i.get("purpose", "") for i in data["icons"])


def test_manifest_icon_srcs_resolve_to_committed_pngs(client):
    from django.contrib.staticfiles import finders

    data = json.loads(client.get("/manifest.webmanifest").content)
    for icon in data["icons"]:
        rel = icon["src"].split("/static/", 1)[1]
        path = finders.find(rel)
        assert path, f"icon not found: {icon['src']}"
        with open(path, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_theme_color_matches_manifest_and_head_links(client):
    data = json.loads(client.get("/manifest.webmanifest").content)
    body = client.get(reverse("chores:login")).content.decode()
    assert '<link rel="manifest" href="/manifest.webmanifest">' in body
    assert f'<meta name="theme-color" content="{data["theme_color"]}">' in body
    assert 'name="mobile-web-app-capable" content="yes"' in body
    assert 'name="apple-mobile-web-app-capable" content="yes"' in body
    assert 'rel="apple-touch-icon"' in body


def test_service_worker_served_at_root_as_javascript(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert resp["Content-Type"].split(";")[0] in (
        "text/javascript",
        "application/javascript",
    )
    body = resp.content.decode()
    assert "addEventListener('fetch'" in body or 'addEventListener("fetch"' in body
    assert "CACHE_VERSION" in body
    assert "skipWaiting" not in body


def test_service_worker_precache_and_activate(client):
    body = client.get("/sw.js").content.decode()
    assert "chores/chores.css" in body
    assert "/offline/" in body
    assert "icon-192.png" in body
    assert "icon-512.png" in body
    assert "apple-touch-icon-180.png" in body
    assert "clients.claim()" in body


def test_offline_route_extends_base(client):
    resp = client.get(reverse("chores:offline"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "<html" in body and "Household Chores" in body
    assert "offline" in body.lower()


def test_registration_script_in_base(client):
    body = client.get(reverse("chores:login")).content.decode()
    assert "'serviceWorker' in navigator" in body
    assert "window.addEventListener('load'" in body
    assert "navigator.serviceWorker.register('/sw.js')" in body
    assert ".catch(" in body
