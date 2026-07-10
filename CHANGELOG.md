# Changelog

All notable changes to artoo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-07-10

Published on PyPI as **`artoo-artifacts`** — the bare `artoo` name is
blocked by a confusable-name collision with the abandoned `ar_too`
project. The import package and the command are `artoo` either way.

First public release. Proven end-to-end on day one: the explainer
generator ran against the public [somm](https://github.com/lavallee/somm)
repo (55k LOC → 15 analysis briefs → 6 pages) and published to GitHub
Pages through the github-pages adapter.

### Added

- Artifact model: `artifact.toml` manifest, `site/` publishable root,
  research backing behind a deny-by-default deploy firewall.
- CLI: `init`, `list`, `status`, `build`, `deploy`, `lib`, `generate`,
  `doctor`.
- Deploy adapters: `github-pages` (legacy `/docs`, workflow, and branch
  modes), `rsync` (named targets, secrets outside the repo), `command`.
- Site libraries: vendored-with-provenance model; built-in `artoo-kit`
  (tokens, base, article layout, components).
- Plugin system: `artoo.generators`, `artoo.deployers`, `artoo.libraries`
  entry-point groups.
- Workers: tiered delegation to local agent CLIs (`codex` for analysis
  fan-out, `claude` for synthesis); no API keys in core.
- `explainer` generator: multi-page repo explainer with deterministic
  inventory, per-module analysis, narrative synthesis, Mermaid diagrams,
  and a build colophon.
- Optional flip integration (`artoo[research]`): generator runs recorded
  as reporter's-notebook sources, claims, and sessions.
