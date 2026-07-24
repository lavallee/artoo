# Changelog

All notable changes to artoo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Changed

- New artifacts use the DES-governed light editorial starter and include a
  private `work/design-brief.md`; artoo-kit 0.2.0 adds explicit editorial type
  roles while keeping existing vendored artifact bytes untouched.
- Explainer planning and page prompts begin from the reader decision, headline
  claim, evidence limits, counter-reading, and licit comparisons instead of
  dashboard-like component composition.
- **artoo-kit 0.3.0**: adds the provenance panel (`components.css` styles +
  `provenance.js` hydrator + in-prose claim anchors), a default `favicon.svg`,
  and a kit `README.md` documenting panel usage plus the SVG `fill="var(--…)"`
  gotcha and chart guidance. Existing vendored bytes are untouched until an
  explicit `artoo lib update artoo-kit`.
- Explainer pages now link the kit favicon, and — when a notebook projection is
  produced — carry the provenance panel and a notebook-aware colophon that names
  the render vintage.

### Added

- **flip roundtrip (read half)** — artoo now *reads* an attached flip notebook
  back out, activating when flip is on `PATH` (or pinned via `ARTOO_FLIP_BIN`)
  and degrading silently when it is absent:
  - **Provenance ingestion.** `artoo provenance <artifact>` (and every non-dry
    `artoo build`) runs `flip export json` and lands the policy-filtered
    `flip-render/1` projection at `site/data/provenance.json`, plus a
    `provenance.js` global loader so the panel hydrates from `file://`. The
    notebook `uid`+`updated` are recorded in `artifact.toml` as the render
    vintage. `--include-private` is used only when the manifest opts in with
    `[research] include_private = true`; otherwise flip's own visibility /
    `source_trail_public` filter is never bypassed.
  - **Provenance panel + colophon** (artoo-kit): a data-driven panel — sources
    with grades/independence, claims with status and verification-method badges,
    counts, notebook vintage and generated stamp — that renders nothing when no
    projection is present.
  - **Claim anchors.** Bracketed flip ids (`[C7]`, `[A3]`, `[F1]`) that exist in
    the projection become stable in-prose anchors (`id="claim-C7"`) linking to
    their panel entry, with the claim text/status as a tooltip. Done client-side
    by the kit, never touching code blocks; ids the projection does not know are
    left alone.
  - **Staleness.** `artoo status` compares the recorded render vintage against
    the live notebook manifest and reports fresh / stale / never-rendered /
    unknown — advisory, never a failure.
  - **Deploy gate.** `artoo deploy` runs `flip doctor --json` on an attached
    notebook; ERROR-level findings block with an actionable message.
    `--allow-doctor-errors` overrides; absent flip or notebook skips with a note.
- `artoo status` and `artoo build` validate every `*.json` under `site/data/`
  and report parse errors as findings.
- `artoo vizier-guide` optionally records a successful local `vizier guide`
  invocation and its complete output in private artifact work files without a
  Vizier import dependency or direct model call.

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
