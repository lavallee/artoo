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

## Install

```bash
uv tool install artoo-artifacts   # or: pipx install artoo-artifacts
artoo --version                   # the command is `artoo`
```

Research-notebook support activates automatically when
[flip](https://github.com/lavallee/flip) is installed alongside artoo.

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

## Generate a repo explainer

```bash
artoo generate explainer --repo . --out site/explainer
artoo deploy site/explainer
```

The explainer inventories the repo deterministically, fans out per-module
analysis to a cheap worker (`codex`), synthesizes the narrative with a strong
worker (`claude`), renders architecture diagrams, and assembles a multi-page
site with the built-in design kit. The result is a dated snapshot with a
colophon saying exactly how it was made.

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
