"""Read-only chore list page with recent activity.

Next-due / overdue state is read through :mod:`chores.recurrence`; last-completed
through :func:`chores.services.last_completed_on`. There is no ``next_due``
column and no recurrence math in this module.
"""

import json

from django.conf import settings
from django.contrib.auth.hashers import is_password_usable
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from chores import recurrence
from chores.auth import (
    clear_login_failures,
    get_current_person,
    login_is_locked,
    record_login_failure,
    require_person,
    run_dummy_pin_check,
)
from chores.models import Chore, Completion, Person, PushSubscription
from chores.services import last_completed_on

RECENT_ACTIVITY_LIMIT = 10

# --- PWA shell -------------------------------------------------------------
#
# Bump CACHE_VERSION in the SAME change as ANY edit to a precached asset
# (chores.css, the offline page, the icons, a vendored HTMX file, or sw.js
# itself). Django serves these at stable, non-hashed URLs, so a cache-first
# service worker would otherwise keep serving the stale copy forever.
CACHE_VERSION = "v2"

THEME_COLOR = "#4a6fa5"
BACKGROUND_COLOR = "#ffffff"

_ICON_192 = "chores/icons/icon-192.png"
_ICON_512 = "chores/icons/icon-512.png"
_ICON_192_MASKABLE = "chores/icons/icon-192-maskable.png"
_ICON_512_MASKABLE = "chores/icons/icon-512-maskable.png"
_APPLE_TOUCH_ICON = "chores/icons/apple-touch-icon-180.png"


def _vendored_htmx_url():
    """Return the static URL of a vendored HTMX file if one is committed.

    #6 (HTMX) is deferred; if the vendor file is not there yet, precache
    still works without it.
    """
    vendor_dir = settings.BASE_DIR / "chores" / "static" / "chores" / "vendor"
    if vendor_dir.is_dir():
        for path in sorted(vendor_dir.glob("htmx-*.min.js")):
            return static(f"chores/vendor/{path.name}")
    return None


def _precache_urls():
    urls = [
        reverse("chores:offline"),
        static("chores/chores.css"),
        static(_ICON_192),
        static(_ICON_512),
        static(_ICON_192_MASKABLE),
        static(_APPLE_TOUCH_ICON),
    ]
    htmx = _vendored_htmx_url()
    if htmx:
        urls.append(htmx)
    return urls


def manifest(request):
    data = {
        "name": "Household Chores",
        "short_name": "Chores",
        "description": "Shared household chore list for the family.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "icons": [
            {"src": static(_ICON_192), "sizes": "192x192", "type": "image/png",
             "purpose": "any"},
            {"src": static(_ICON_512), "sizes": "512x512", "type": "image/png",
             "purpose": "any"},
            {"src": static(_ICON_192_MASKABLE), "sizes": "192x192",
             "type": "image/png", "purpose": "maskable"},
            {"src": static(_ICON_512_MASKABLE), "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(
        json.dumps(data, indent=2),
        content_type="application/manifest+json",
    )


def service_worker(request):
    return render(
        request,
        "chores/sw.js",
        {
            "cache_version": CACHE_VERSION,
            "precache_urls": json.dumps(_precache_urls()),
        },
        content_type="text/javascript",
    )


def offline(request):
    return render(request, "chores/offline.html")

LOGIN_ERROR = "That didn't match, try again"
# Shown when the pair/IP is in a lockout cooldown. One combined generic message:
# it names neither the person, the field, nor the exact remaining time.
LOGIN_LOCKED_ERROR = f"{LOGIN_ERROR} Too many attempts, try again later."


def _safe_next(request, raw_next):
    if raw_next and url_has_allowed_host_and_scheme(
        raw_next,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return raw_next
    return None


def login(request):
    people = sorted(Person.objects.all(), key=lambda p: p.name.casefold())

    if request.method == "GET":
        if get_current_person(request) is not None:
            return redirect("chores:list")
        return render(
            request,
            "chores/login.html",
            {"people": people, "next": request.GET.get("next", "")},
        )

    raw_next = request.POST.get("next", "")
    person_id = request.POST.get("person_id", "")
    pin = request.POST.get("pin", "")

    person = Person.objects.filter(pk=person_id).first() if person_id else None
    client_ip = request.META.get("REMOTE_ADDR") or "0.0.0.0"

    def _reject(error):
        return render(
            request,
            "chores/login.html",
            {
                "people": people,
                "next": raw_next,
                "selected_person_id": person_id,
                "error": error,
            },
            status=200,
        )

    # Refuse a locked pair/IP before the PIN is looked at: a correct PIN during
    # lockout still does not sign in. Spend an equivalent hash comparison so the
    # locked path's latency matches the wrong-PIN path.
    if login_is_locked(person, client_ip):
        run_dummy_pin_check()
        return _reject(LOGIN_LOCKED_ERROR)

    ok = (
        person is not None
        and is_password_usable(person.pin_hash)
        and person.check_pin(pin)
    )
    if not ok:
        record_login_failure(person, client_ip)
        return _reject(LOGIN_ERROR)

    clear_login_failures(person, client_ip)
    request.session["person_id"] = person.id
    request.session.cycle_key()
    request._current_person = person

    target = _safe_next(request, raw_next)
    return redirect(target) if target else redirect("chores:list")


@require_POST
def logout(request):
    request.session.flush()
    return redirect("chores:login")


def _cadence_label(chore):
    if chore.cadence == Chore.Cadence.CUSTOM:
        return f"Every {chore.custom_interval_days} days"
    return Chore.Cadence(chore.cadence).label


def _build_row(chore, today):
    last = last_completed_on(chore)
    due = recurrence.next_due(
        chore.cadence, chore.anchor_date, last, chore.custom_interval_days
    )
    overdue = recurrence.is_overdue(due, today)
    return {
        "title": chore.title,
        "cadence_label": _cadence_label(chore),
        "last_completed": last,
        "next_due": due,
        "is_overdue": overdue,
        "is_due_today": due == today and not overdue,
        "claimed_by_name": (
            chore.claimed_by.name
            if chore.is_pooled and chore.claimed_by is not None
            else None
        ),
    }


# --- Web push subscription flow (#9) --------------------------------------


@require_person
def settings_view(request):
    """Settings page: enable browser notifications for this device."""
    return render(
        request,
        "chores/settings.html",
        {"vapid_public_key": settings.VAPID_PUBLIC_KEY},
    )


@require_POST
@require_person
def push_subscribe(request):
    """Upsert the current person's Web Push subscription, keyed by endpoint.

    ``require_POST`` is outermost so ``GET``/``PUT``/``DELETE`` get a 405
    regardless of auth; an unauthenticated ``POST`` falls through to
    ``require_person`` and is redirected to the sign-in page.
    """
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"error": "body is not valid JSON"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "expected a JSON object"}, status=400)

    endpoint = payload.get("endpoint")
    keys = payload.get("keys") or {}
    p256dh = keys.get("p256dh") if isinstance(keys, dict) else None
    auth = keys.get("auth") if isinstance(keys, dict) else None
    if not endpoint or not p256dh or not auth:
        return JsonResponse(
            {"error": "endpoint, keys.p256dh and keys.auth are required"},
            status=400,
        )

    person = get_current_person(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    _, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "person": person,
            "p256dh": p256dh[:255],
            "auth": auth[:255],
            "user_agent": user_agent,
        },
    )
    status = "created" if created else "updated"
    return JsonResponse({"status": status}, status=201 if created else 200)


@require_person
def chore_list(request):
    today = timezone.localdate()

    chores = Chore.objects.select_related("owner", "claimed_by").prefetch_related(
        "completions"
    )

    owner_groups = {}
    pool_rows = []
    for chore in chores:
        row = _build_row(chore, today)
        if chore.owner is None:
            pool_rows.append(row)
        else:
            owner_groups.setdefault(chore.owner.name, []).append(row)

    groups = []
    for name in sorted(owner_groups, key=str.casefold):
        rows = sorted(owner_groups[name], key=lambda r: r["title"].casefold())
        groups.append({"heading": name, "rows": rows})
    if pool_rows:
        groups.append(
            {
                "heading": "Pool",
                "rows": sorted(pool_rows, key=lambda r: r["title"].casefold()),
            }
        )

    completions = list(
        Completion.objects.select_related("chore", "person")[:RECENT_ACTIVITY_LIMIT]
    )
    activity = [
        {
            "chore_title": c.chore.title,
            "person_name": c.person.name,
            "completed_at": timezone.localtime(c.completed_at),
        }
        for c in completions
    ]

    context = {
        "groups": groups,
        "has_chores": chores.exists(),
        "activity": activity,
    }
    return render(request, "chores/chore_list.html", context)
