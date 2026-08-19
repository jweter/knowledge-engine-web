# Quality Preflight

Knowledge Engine treats recurring CI failures as engineering signals, not isolated cleanup work (see `knowledge-engine-core`'s issue [#371](https://github.com/jweter/knowledge-engine-core/issues/371), the project-wide rule this script implements for this repository). Before opening or updating a pull request that changes Python, run the canonical local preflight from the repository root:

```sh
poetry run python scripts/quality_preflight.py
```

The preflight runs the deterministic, Poetry-managed gates in the same order as `.github/workflows/quality.yml`'s `checks` job:

1. `ruff format --check .`
2. `ruff check .`
3. `mypy knowledge_engine_web tests`
4. `pytest`
5. `pip-audit`
6. `git diff --check` (diff hygiene)

It stops on the first failure so the first actionable defect stays visible. Fix that root cause, run the preflight again, and only then push the PR update. GitHub Actions remains the authoritative merge gate.

This intentionally does not attempt the `checks` job's sibling `docker` job (building `knowledge-engine-web-alpha` and smoke-testing the running container) -- that step is not Poetry-managed and CI itself is the right place to run it. If a change plausibly affects the Docker image (`Dockerfile`, `pyproject.toml`, `data/` snapshot contents), build and smoke-test it locally too:

```sh
docker build -t knowledge-engine-web-alpha:local .
docker run -d --name alpha-smoke-test -p 8000:8000 \
  -e KE_WEB_ALPHA_USERNAME=ci -e KE_WEB_ALPHA_PASSWORD=ci \
  knowledge-engine-web-alpha:local
curl -sf -u ci:ci http://127.0.0.1:8000/graph > /dev/null && echo "Container responded."
docker rm -f alpha-smoke-test
```

## Recurring-failure rule

This mirrors the same preventive pattern already adopted in `knowledge-engine-ai` (`scripts/preflight.py`, `docs/preflight.md`) and `knowledge-engine-core` (`scripts/quality_preflight.py`, `docs/quality_preflight.md`) -- issue #371 explicitly named this as "a cross-repository engineering rule for `knowledge-engine-core`, `knowledge-engine-ai`, and `knowledge-engine-web`," and this repository was the one still missing it. Cheap deterministic checks should run locally before consuming a CI cycle, catching the exact class of connector/agent-authored formatting, lint, import-order, and typing failures that issue tracked recurring across the family.

Do not weaken CI, suppress diagnostics, or broaden ignore rules merely to make the preflight pass.
