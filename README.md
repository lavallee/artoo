# artoo

**Generate and manage artifacts** — self-contained HTML mini-sites that pair
presentation with the research backing it.

There's a burgeoning practice of getting explanations of systems out of LLMs
as real pages — with navigation, diagrams, and provenance — instead of
markdown dumps, and of composing reports from multiple assets. artoo is the
tool layer for that practice:

- **Artifacts live anywhere.** An artifact is a directory with an
  `artifact.toml` inside whatever repo owns it. A library's explainer lives
  in that library's repo. One repo can hold many artifacts.
- **Self-contained, with provenance.** The publishable `site/` renders from
  a `file://` URL — vendored assets, no bundler, no CDN dependencies. Shared
  components come from versioned, hash-pinned site libraries you can upgrade
  deliberately.
- **Deployment-aware.** artoo understands GitHub Pages (including whether
  your repo serves from `/docs`, a workflow, or a branch), ssh/rsync targets,
  and arbitrary publish commands. Secrets never enter the repo.
- **Research stays with the piece.** Notebooks, working files, and anything
  `_`-prefixed sit next to the presentation but can never ship — the deploy
  path is deny-by-default.
- **Generators, not API keys.** Model-powered generators (like the repo
  explainer) delegate to agent CLIs you already have — `claude`, `codex` —
  with cheap tiers for fan-out analysis and strong tiers for synthesis.
  artoo core makes no model calls and holds no keys.
- **DES governs the public-artifact default.** New work starts as a light,
  long-form editorial argument with an explicit reader decision, evidence
  limits, and valid comparisons. Artoo remains responsible for packaging,
  provenance, the private-file firewall, and deployment.

## Install

```bash
uv tool install artoo-artifacts   # or: pipx install artoo-artifacts
artoo --version                   # the command is `artoo`
```

Research-notebook support activates automatically when
[flip](https://github.com/lavallee/flip) is installed alongside artoo — both
the write half (generator runs recorded as sources/claims/sessions) and the
read half (below). artoo discovers flip on `PATH`; pin a specific build with
`ARTOO_FLIP_BIN`. With no flip installed, artoo core works unchanged.

## Provenance roundtrip

When an artifact declares an attached notebook (`[research] notebook = "…"`),
artoo reads it back out at build time:

```bash
artoo provenance site/my-report   # flip export json → site/data/provenance.json
artoo status site/my-report       # ... and reports if the render is stale
```

`artoo build` refreshes `site/data/provenance.json` (flip's policy-filtered
`flip-render/1` projection) and records the notebook `uid`+`updated` in
`artifact.toml` as the render vintage. The artoo-kit **provenance panel**
renders that data — sources with grades, claims with status and
verification-method badges, counts, and the notebook vintage — and turns
bracketed flip ids (`[C7]`) in prose into stable anchors that link to their
panel entry. `artoo deploy` runs `flip doctor` on the notebook first and blocks
on ERROR-level findings (`--allow-doctor-errors` overrides). The projection is
filtered by flip itself; artoo only passes `--include-private` when the manifest
sets `[research] include_private = true`. All of it no-ops cleanly without flip.

### The structural verbs

Two verbs make the loop bidirectional:

```bash
# Read direction: render a report FROM a canonical flip notebook.
artoo generate notebook-report --notebook path/to/notebook --out site/report

# Reverse direction: route a correction back INTO the notebook (never edits site/).
artoo feedback site/report "C7 overstates the effect" --claim C7
```

`generate notebook-report` is fully deterministic (no model calls). It renders
the notebook's current draft (`drafts/current`, else newest `drafts/vN`) to HTML,
or — with no draft — an honest structured skeleton (questions, claims by status,
sources by grade). The notebook is canonical; re-running regenerates the page in
place, so **edits belong in the notebook, not the render** (the colophon says so).
`--include-private` renders a non-public notebook in full.

`artoo feedback` never touches `site/`: it opens a flip question (default) or a
`flip log` event (`--as-log`) in the attached notebook, carrying the artifact ref
and any cited id. A cited `--claim`/`--source` id is verified against the notebook
and refused if unknown (typo protection); a private breadcrumb is recorded in
`work/feedback.jsonl`.

## Quickstart

```bash
# Scaffold an artifact inside any repo
artoo init site/my-report --kind report --title "Q3 systems report"

# See every artifact in the repo
artoo list

# Check health: manifest, firewall, library drift
artoo status site/my-report

# Publish (adapter chosen by the manifest's [deploy] table)
artoo deploy site/my-report
```

`artoo init` also creates `work/design-brief.md`, a private authoring contract
for the reader decision, headline claim, evidence boundaries, data vintages,
licit comparisons, forms, DES references, and proof required. It never enters
the deployable `site/` tree.

## Optional Vizier guidance

[Vizier](https://github.com/lavallee/vizier) is an optional local companion for
implementation critique and form selection. If its keyless `vizier` CLI is
installed, Artoo can run `vizier guide` and retain the full invocation and
output behind the artifact firewall:

```bash
artoo vizier-guide \
  "compare district spending over time without hiding enrollment change" \
  --context "Headline, caption, source, and implementation constraints" \
  --family "Change over time" --series-count 4 \
  --form-count 3 --prior-count 5 --no-semantic \
  --artifact site/my-report
```

The receipt is `work/vizier-guidance.md`. Artoo shells out to the installed CLI;
Vizier is not an Artoo dependency, and this path makes no direct model or API
call. Vizier advises on visual form and implementation. DES remains the design
authority, while Artoo owns artifact packaging, provenance, and deployment.

A clean `artoo build` proves build-command and artifact/firewall integrity. It
does not prove visual or editorial acceptance; review the rendered artifact
against its design brief and DES reference before publishing.

## Generate a repo explainer

```bash
artoo generate explainer --repo . --out site/explainer
artoo deploy site/explainer
```

The explainer inventories the repo deterministically, fans out per-module
analysis to a cheap worker (`codex`), synthesizes the narrative with a strong
worker (`claude`), renders architecture diagrams, and assembles a multi-page
site with the built-in design kit. Planning starts from a named reader decision,
supportable headline claim, counter-reading, and licit comparisons before it
selects tables or figures. The result is a dated snapshot with a colophon saying
exactly how it was made.

## Status

v0.1.0 — alpha. The manifest format, CLI surface, and plugin entry points
are young and may change before 1.0. See [DESIGN.md](DESIGN.md) for the
architecture and [CHANGELOG.md](CHANGELOG.md) for history.

## Development

```bash
git clone https://github.com/lavallee/artoo && cd artoo
uv sync
uv run pytest -q
uv run ruff check src tests
```

MIT licensed. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
