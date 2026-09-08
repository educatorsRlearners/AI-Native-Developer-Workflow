# Web push

A signed-in person enables browser notifications from `/settings/`. Their
browser's Web Push subscription is saved as a `PushSubscription` row (one per
browser, keyed by `endpoint`). The service worker (`sw.js`) knows how to show a
notification and what to do when it is clicked.

**No push is sent from application code yet.** Signing and sending a push needs
`pywebpush`, which arrives in #11 and is *not* a dependency of this project yet.
Everything below uses throwaway tools run with `uvx` / `pipx` / `openssl` -
never `uv add`.

## Pieces

- `config/settings.py` reads `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`,
  `VAPID_ADMIN_EMAIL` from the env via `django-environ`, each defaulting to an
  empty string so `runserver` and `pytest` start without them.
- `.env.example` carries placeholders for all three.
- The **public** key is handed to the browser as a `data-vapid-key` attribute on
  the enable button in `chores/templates/chores/settings.html`. The **private**
  key is never rendered into a template or sent to the client.
- `chores/static/chores/push.js` (vendored, no CDN) drives the button and calls
  `chores:push-subscribe`.
- `chores/models.py::PushSubscription` + read-only admin.
- `sw.js` `push` / `notificationclick` listeners.

## Generate a VAPID keypair (one-off)

Using the `py-vapid` CLI without installing it into the project:

```sh
uvx --from py-vapid vapid --gen
uvx --from py-vapid vapid --applicationServerKey
```

`vapid --gen` writes `private_key.pem` / `public_key.pem` in the current
directory. `--applicationServerKey` prints the base64url public key to paste
into `.env` as `VAPID_PUBLIC_KEY`. For `VAPID_PRIVATE_KEY`, use the DER/base64url
private key that `py-vapid` emits (`vapid --sign` reads `private_key.pem`; #11
will wire the exact form it needs).

Pure-`openssl` alternative:

```sh
openssl ecparam -name prime256v1 -genkey -noout -out vapid_private.pem
openssl ec -in vapid_private.pem -pubout -outform DER 2>/dev/null \
  | tail -c 65 | base64 | tr '+/' '-_' | tr -d '='   # -> VAPID_PUBLIC_KEY
openssl ec -in vapid_private.pem -outform DER 2>/dev/null \
  | base64 | tr '+/' '-_' | tr -d '='                # -> VAPID_PRIVATE_KEY
```

Set `VAPID_ADMIN_EMAIL` to a real `mailto:` contact for the push service.

Delete the `.pem` files afterwards - only the `.env` values are kept, and
`.env` is git-ignored.

## Fire one manual test push (proves the plumbing)

1. Enable notifications on `/settings/` in a browser so a row exists:
   `python manage.py shell -c "from chores.models import PushSubscription; print(PushSubscription.objects.count())"`
2. Send one push by hand with a transient `pywebpush` (NOT committed, NOT a
   dependency):

```sh
uvx --with pywebpush python - <<'PY'
import os, json, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
from pywebpush import webpush
from chores.models import PushSubscription

sub = PushSubscription.objects.latest("updated_at")
webpush(
    subscription_info={
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    },
    data=json.dumps({"title": "Chores", "body": "Test push", "url": "/"}),
    vapid_private_key=settings.VAPID_PRIVATE_KEY,
    vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
)
print("sent")
PY
```

3. Expected: the OS notification appears; clicking it focuses/opens the app at
   the chore list. Record the outcome in the PR description.

## Known gaps (out of scope here)

- **Subscription expiry:** when a real send later gets `410 Gone` / `404`, the
  dead row should be pruned. That is #11; this issue does not prune.
- **Unsubscribe UI:** turning notifications back off from the settings page is
  #24.
- **Actually sending on a schedule / deciding who to nag:** #11 / #12.
