# Household Chore Tool — MVP Task Backlog

Stack (decided): Django + HTMX, server-rendered templates, SQLite, `django-q2`
for scheduled jobs, `pywebpush` for web push, deployed as one container.

Scope: the **first usable version** for two people. Tasks are ordered so
dependencies come first, but each is written to be picked up without reading the
others. Where a task depends on a model or function from an earlier one, it names
it.

## 1. Empty project with a passing test
Goal: A runnable Django project with tooling and one green test.
Description: Scaffold a Django 5.x project (`config/` settings package, SQLite,
`chores` app), add `pytest` + `pytest-django`, `ruff`, and a `.env` loader
(`django-environ`). Include one trivial test that passes via `pytest`, plus a
README section on how to run the dev server and the tests.

## 2. Core models and seed data
Goal: Store the two people and their chores.
Description: Add a `Person` model (name, email, hashed PIN, timestamps) and a
`Chore` model (title, optional `owner` FK to `Person` where null = free-for-all
pool, a `cadence` choice of daily/weekly/monthly/custom, `custom_interval_days`,
`anchor_date`). Register both in the Django admin. Add a management command that
seeds the two people. Model tests cover owned vs pooled chores.

## 3. Recurrence engine (pure functions)
Goal: Compute when a chore is next due and whether it is overdue.
Description: Write pure functions in `chores/recurrence.py` taking a chore's
cadence + `anchor_date` + last-completion date and returning `next_due` and
`is_overdue(as_of)`. No models imported, no views. Thorough unit tests for
daily/weekly/monthly/custom and the never-completed case.

## 4. Completion model, complete, and claim
Goal: Log every completion with who and when; let a person claim a pooled chore.
Description: Add a `Completion` model (FK `Chore`, FK `Person`, `completed_at`).
Add service functions `complete_chore(chore, person, when)` (writes a
`Completion`; next-due follows from the task 3 engine) and `claim_chore(chore,
person)` (assigns the current cycle's doer for a pooled chore). Unit-test that
completing logs a row and shifts the due date.

## 5. Chore list page with recent activity
Goal: One server-rendered page showing all chores and what was done lately.
Description: Add a base template (semantic HTML, one small CSS file), a chore
list view + URL grouping chores by owner and pool with each chore's cadence and
due/overdue status (task 3 engine), plus a short "recent completions" list from
the `Completion` rows (task 4). Static, no interactivity yet. View test asserts
chores and completions render.

## 6. HTMX complete and claim interactions
Goal: Mark a chore done or claim a pooled chore without a full page reload.
Description: Add HTMX endpoints and partial templates so "Complete" calls
`complete_chore` (task 4) and swaps in the updated row, and "Claim" on a pooled
chore calls `claim_chore`. Test the endpoints return the updated partial.

## 7. PIN authentication
Goal: Each person signs in without a full account system.
Description: Add a PIN entry screen checked against the hashed PIN from task 2,
set a session on success, and add logout plus a "current person" helper for
views and templates. Gate the chore views so an unauthenticated request is
redirected to the PIN screen. Tests cover redirect and successful sign-in.
(Magic-link login is out of scope for the MVP — see below.)

## 8. Installable PWA shell
Goal: The app can be added to the home screen and launches standalone.
Description: Add `manifest.webmanifest` (name, icons in the required sizes,
`display: standalone`, theme colors), link it from the base template, add icon
assets, and register a service worker that caches the app shell. Document the
iOS "Add to Home Screen" requirement from `_docs/plan.md` (web push on iOS needs
it).

## 9. Web push subscription flow
Goal: Store a browser's push subscription against a person.
Description: Generate VAPID keys (config via env), add a `PushSubscription`
model (FK `Person`, endpoint, keys), a JS subscribe flow triggered from a
profile/settings page, and an endpoint that saves the subscription. Extend the
task 8 service worker to handle `push` events and show a notification. Test the
save endpoint.

## 10. Email nag delivery
Goal: Send a chore nag by email.
Description: Configure Django's email backend for an env-driven SMTP provider
(console backend in dev). Add `send_nag_email(person, chores)` with plain + HTML
templates. Unit-test that one message goes to the right address listing the
chore titles.

## 11. Web push nag delivery
Goal: Deliver a nag to a person's registered browsers.
Description: Add `send_push(person, chores)` using `pywebpush` and the
`PushSubscription` rows from task 9, deleting subscriptions that return 404/410.
Unit-test with `pywebpush` mocked: one call per active subscription, cleanup on
a gone response.

## 12. Nightly overdue sweep job
Goal: Automatically find overdue chores and nag the right people each day.
Description: Add `django-q2` to settings and a scheduled task that runs the task
3 recurrence check across all chores, builds a `Person -> [chores]` map (owned
chore → owner only; pooled chore → both people, de-duplicated), and calls
`send_push` (task 11) and `send_nag_email` (task 10) per person. Add a
management command to run the sweep once on demand. Test the orchestration with
the senders mocked.

## 13. Containerized deployment
Goal: One image runs the whole app.
Description: Add a `Dockerfile` and a process definition running the web server
and the `django-q2` cluster, a persistent volume for the SQLite file, env-var
docs (VAPID keys, SMTP, secret key), and a deploy config for Fly.io or Railway.
Document first-deploy steps (migrate, seed people from task 2).

---

## Out of scope for the MVP
- **Magic-link login** — PIN auth (task 7) is enough for v1; add magic links later.
- **Custom-cadence UI** — the `custom_interval_days` field exists (task 2) but
  the first version only needs daily/weekly/monthly pickers; custom can be set
  via the admin.
- **Dedicated filterable/paginated completion history** — task 5 shows recent
  activity inline; a full history page can come later.
- **Alpine.js** — HTMX alone covers every MVP interaction.
- **Per-person notification preferences / quiet hours** — always nag for now.
