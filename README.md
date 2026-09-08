# AI-Native-Developer-Workflow

Household chore tracking tool — a Django-backed installable PWA. See
`_docs/plan.md` for scope.

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
uv sync                       # install dependencies
cp .env.example .env          # local configuration (optional; sane defaults apply)
uv run python manage.py migrate
uv run python manage.py runserver   # dev server at http://127.0.0.1:8000/
```

## Onboarding a household member

People are created (with no usable PIN) by `seed_people`. Before someone can
sign in, give them a PIN:

```bash
uv run python manage.py set_pin alex@example.com   # prompts for the PIN twice
```

Until `set_pin` has been run for a person, sign-in for them fails with the same
generic error as a wrong PIN. Sign in at `/login/`; sign out from the header.

## Tests

```bash
uv run pytest                 # whole suite
uv run pytest chores/tests/test_smoke.py   # a single file
```

Lint with `uv run ruff check .`.
