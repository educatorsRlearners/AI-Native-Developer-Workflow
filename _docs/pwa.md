# PWA shell

The app is an installable PWA: add-to-home-screen, standalone launch, and an
offline app shell served by a hand-written service worker. No build step, no
bundler, no service-worker library.

## Pieces

- `GET /manifest.webmanifest` (`config/urls.py` -> `chores.views.manifest`) --
  root scope, `application/manifest+json`.
- `GET /sw.js` (`config/urls.py` -> `chores.views.service_worker`) -- rendered
  from `chores/templates/chores/sw.js`, served from the root so its control
  scope is `/`.
- `GET /offline/` (`chores:offline`) -- the offline fallback page, extends
  `base.html`; its only sub-resource is `chores.css`, which is precached.
- Icons: `chores/static/chores/icons/` (192, 512, 192/512 maskable, 180
  apple-touch). All committed, none fetched remotely.
- Registration: an inline `<script>` at the end of `base.html`, guarded by
  `'serviceWorker' in navigator`, run on `window` `load`, failures logged.

## Cache invalidation: bump `CACHE_VERSION`

`sw.js` uses a cache-first strategy for shell assets, and Django serves those
assets at stable, non-hashed URLs (`/static/chores/chores.css`, the icons,
`/offline/`, a vendored HTMX file, and `/sw.js` itself). A cache-first SW would
therefore keep serving the old copy forever.

**Release step:** any change to a precached asset -- CSS, the offline page, an
icon, the vendored HTMX file, or `sw.js` -- must bump `CACHE_VERSION` in
`chores/views.py` in the *same* change. On the next visit the browser sees a
byte-different `sw.js`, installs it, and `activate` deletes every cache whose
name is not the current version.

## HTMX (#6) is optional here

#6 is deferred. The precache list is built server-side: if
`chores/static/chores/vendor/htmx-<version>.min.js` exists it is added to the
list, otherwise `install` still succeeds without it. When #6 lands, committing
the vendored file plus a `CACHE_VERSION` bump is all that is needed.

## First-ever load while offline

If the service worker has never installed (brand-new device, never opened the
app online), an offline visit shows the browser's own offline error page. This
is expected and is not worked around -- there is nothing cached yet.

## iOS constraints (groundwork for #9 web push)

- Web push on iOS Safari (#9) works **only** after the user adds the PWA to the
  home screen. This is carried over from `_docs/plan.md`.
- iOS has no `beforeinstallprompt` and shows no install banner. Installing is a
  manual **Share > Add to Home Screen**.
- iOS evicts service-worker caches after roughly 7 unused days and caps origin
  storage at about 50 MB, so the offline shell is best-effort on iOS.

## Testing install / offline from a phone

Service workers register on `http://localhost` and `http://127.0.0.1` but
**not** over plain HTTP on a LAN IP (`http://192.168.x.x`). To test
install/offline from a phone on the LAN you need HTTPS -- a tunnel (e.g.
Cloudflare Tunnel / ngrok) or a self-signed cert with `runserver_plus`.

## Manual verification (record in the PR)

- Chrome DevTools > Application > Manifest: manifest shown, no errors, icons
  listed.
- Application > Service Workers: `sw.js` activated.
- Address-bar install control offered; installing opens a standalone window
  whose start page is the chore list.
- Load `/` warm, then DevTools > Network > Offline, reload `/`: chore list
  still renders from cache (no browser error page).
