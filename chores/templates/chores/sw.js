{% load static %}// Hand-written service worker for the Household Chores PWA shell.
// No build step, no bundler, no Workbox. Edit this file directly.
//
// IMPORTANT: any change to a precached asset (chores.css, the offline page,
// the icons, a vendored HTMX file, or this file itself) MUST bump
// CACHE_VERSION in the same change -- Django serves these at stable,
// non-hashed URLs, so a cache-first SW would otherwise pin the stale copy.
// See _docs/pwa.md.

const CACHE_VERSION = "{{ cache_version }}";
const SHELL_CACHE = "chores-shell-" + CACHE_VERSION;
const RUNTIME_CACHE = "chores-runtime-" + CACHE_VERSION;

const OFFLINE_URL = "{% url 'chores:offline' %}";

// App-shell asset list. HTMX (#6) is included by the server only if a
// vendored file is committed; if it is absent, install still succeeds.
const PRECACHE_URLS = {{ precache_urls|safe }};

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  // Deliberately not activating early: a new service worker stays in
  // "waiting" until every tab of the app is closed and reopened, so a deploy
  // never swaps assets out from under an open session. (No skip-waiting call.)
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name !== SHELL_CACHE && name !== RUNTIME_CACHE)
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Non-GET (POST to complete/claim, the sign-in form, ...) never touches
  // the cache.
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // Navigation requests: network-first, fall back to the cached copy of that
  // URL, then to the offline page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches
            .match(request)
            .then((cached) => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

  // Precached shell assets: cache-first, network fallback.
  if (PRECACHE_URLS.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request))
    );
    return;
  }

  // Everything else falls through to the network, uncached.
});
