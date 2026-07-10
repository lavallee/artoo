# Releasing artoo

1. `uv run pytest -q` and `uv run ruff check src tests` pass locally.
2. Bump the version in **both** places, in lockstep:
   - `pyproject.toml` → `[project] version`
   - `src/artoo/__init__.py` → `__version__`
3. Update `CHANGELOG.md`: dated heading, Added/Changed/Fixed sections.
4. Update the landing page (`docs/index.html`) version badge and any new
   capabilities.
5. Commit a clean `chore(release): X.Y.Z`.
6. Tag: `git tag -a vX.Y.Z -m "artoo X.Y.Z"` → push `main` and the tag.
7. `gh release create vX.Y.Z` with focused notes and a compare link.
8. Publishing the release triggers `.github/workflows/publish.yml`
   (PyPI trusted publishing via the `pypi-artoo-artifacts` environment;
   the distribution is `artoo-artifacts`, import/CLI stay `artoo`). Verify the
   run; re-dispatch with `gh workflow run publish.yml` if needed.
   Fallback: `uv build && uv publish` with a token.

Semantic versioning:

- **Patch** — fixes, docs; no surface change.
- **Minor** — new backward-compatible surface (CLI command, adapter,
  entry point, manifest field with a default).
- **Major** — breaking CLI flags, manifest schema, or entry-point
  signatures. Changes to firewall semantics are always breaking.
