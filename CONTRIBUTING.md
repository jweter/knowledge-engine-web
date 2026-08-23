# Contributing

Thank you for helping build Knowledge Engine Web. This project follows
`knowledge-engine-core`'s own development philosophy: favor clear, tested,
well-documented changes over clever shortcuts, and never guess at a piece
of evidence's meaning -- see "The Seam" in `README.md` before touching
anything that renders `core`'s data.

We are not optimizing for getting code written quickly. We are optimizing for
the project still being healthy in 10 years.

## Development Workflow

1. Open or choose an issue before starting non-trivial work.
2. Create a branch from `main`.
3. Make a focused change.
4. Add or update tests.
5. Run the repository preflight.
6. Open a pull request.

After the initial bootstrap, avoid committing directly to `main`. Use feature
branches and pull requests even for small changes.

## Branch Names

Use short, descriptive branch names:

- `feature/graph-summary-page`
- `fix/evidence-report-escaping`
- `docs/local-setup`
- `chore/dependency-bump`

## Commit Messages

Use Conventional Commits:

- `feat: add graph summary page`
- `fix: escape evidence record fields in templates`
- `docs: document local setup`
- `test: cover empty graph rendering`
- `chore: bump knowledge-engine-core pin`

## Quality Preflight

Before opening or updating a Python pull request, run:

```bash
poetry install
poetry run python scripts/quality_preflight.py --fix
```

For deployment-sensitive changes, also build the production image locally:

```bash
poetry run python scripts/quality_preflight.py --fix --docker
```

The preflight safely normalizes Ruff formatting/lint first, then runs the same
Poetry-managed gates as CI: format check, lint, strict mypy, pytest, pip-audit,
and diff hygiene. `--docker` adds the repository-specific production image build.
GitHub Actions remains authoritative and still performs the full container smoke test.

## Code Style

- Prefer readable, typed Python.
- Keep modules focused and small where practical.
- Avoid global mutable state.
- Add docstrings for public classes and functions.
- Never compute, infer, or display a confidence rating, synthesis, or
  judgment about what evidence means -- that seam stays with the
  `knowledge-engine-ai` layer. See `README.md`'s "The Seam" section.

## Tests

Tests should be small, deterministic, and offline. Build fixture databases
with `knowledge_engine`'s own repositories directly; do not commit real
corpus data.

## Architecture Decisions

Record significant decisions in `docs/`, mirroring `knowledge-engine-core`'s
own design-doc-before-code discipline (see `docs/web_design.md`).
