# Contributing

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/).

    uv sync

## Quality gate

All commands must pass before every commit / PR:

    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    uv run pytest -q

CI runs the same gate on Python 3.12 and 3.13.

## Conventions

- Conventional-commit style messages (`feat:`, `fix:`, `chore:`, …).
- Fully typed (`mypy --strict`); public API changes need tests.
- Tests use aioresponses — never call the live Nature API from tests.
- POST bodies are form-encoded (`data=`), never JSON; this mirrors the real
  Nature Cloud API.

## Releases (maintainer)

Bump `version` in `pyproject.toml`, tag `vX.Y.Z`, push the tag — CI publishes
to PyPI via trusted publishing.
