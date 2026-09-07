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

## Tests

```bash
uv run pytest                 # whole suite
uv run pytest chores/tests/test_smoke.py   # a single file
```

Lint with `uv run ruff check .`.
