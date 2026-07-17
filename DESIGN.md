# artoo — design

artoo generates and manages **artifacts**: self-contained, publishable HTML
bundles (mini-sites) that pair presentation with the research that backs it.
It is the tool layer for a growing practice: getting explanations of systems
out of LLMs as real pages — with navigation, diagrams, and provenance —
instead of markdown dumps, and composing reports from multiple assets.

This document records the v0.1 architecture and the reasoning behind it.

## Lineage

artoo generalizes patterns proven in weaver, a private static-site research
workbench by the same author, and adopts the packaging
conventions of its public siblings [vizier](https://github.com/lavallee/vizier),
[somm](https://github.com/lavallee/somm), and
[flip](https://github.com/lavallee/flip). The load-bearing ideas imported:

- **Descriptor as source of truth.** Every artifact carries a small TOML
  manifest; everything else (listings, graphs, deploy routing) is derived
  from it, never hand-maintained.
- **The private-file firewall.** Research notes, notebooks, and anything
  `_`- or `.`-prefixed sit *next to* the presentation but never publish.
  Evidence lives with the piece; the deploy path is deny-by-default.
- **Named deploy targets, per-artifact routing.** The mechanism (rsync/ssh,
  Pages, command) is generic; the values (hosts, users, paths) are local
  config that never enters the repo.
- **Kind-aware scaffolding.** New artifacts start from an archetype
  (explainer, report, reference guide, …) with an appropriate skeleton and
  a research notebook stamped in.
- **Revision snapshots.** Publishing is preceded by cheap local snapshots
  so any shipped state can be diffed and recovered.

Where artoo deliberately departs from its ancestor:

- **Artifacts live anywhere.** The ancestor housed all projects in one
  repo under `projects/`. artoo artifacts live inside whatever repo owns
  them — a library's explainer lives in that library's repo — and one repo
  can hold many artifacts. artoo is installed once and invoked anywhere.
- **No bundler.** Artifacts are self-contained static sites: vendored
  assets, system font stacks, no build-time JS toolchain. What you commit
  is what ships. (A manifest may declare build *commands* — e.g. "export
  this dataset to JSON" — but artoo itself never requires Node or a
  bundling step.)
- **No direct model calls in core.** Like its ancestor, artoo core is a
  renderer/manager. Generators delegate model work to *worker CLIs* the
  user already has (`claude`, `codex`), selected per task tier. artoo
  never holds API keys.

## Concepts

### Artifact

An artifact is a directory marked by an `artifact.toml`. Canonical shape:

```
my-explainer/
  artifact.toml     # the manifest (source of truth)
  site/             # the publishable mini-site — self-contained
    index.html
    style.css
    lib/            # vendored site libraries (managed, see below)
  notebook/         # research backing (flip notebook) — never deployed
  work/             # design brief, guidance, generator files — never deployed
```

`site/` is committed. It must render from a file:// URL or any static
host — no external requests required (CDN references are allowed only in
`vendor`-recorded fallbacks). Everything outside `site/` is backing
material and never leaves the repo.

### Manifest (`artifact.toml`)

```toml
[artifact]
slug = "chart-forms"
title = "Chart forms — when, how, and when not"
description = "A guide to 43 chart-form patterns."
kind = "reference-guide"      # explainer | report | reference-guide | ...
status = "live"               # draft | building | live | archived
created = "2026-07-10"

[build]
# Optional commands that refresh generated inputs before deploy.
commands = ["vizier patterns export -o site/data.json"]
site = "site"                 # publishable root, relative to the manifest

[research]
notebook = "notebook"         # optional flip notebook directory

[deploy]
target = "github-pages"

[deploy.github-pages]
# artoo inspects the repo's actual Pages configuration and routes
# accordingly: legacy /docs serving, an Actions workflow, or a branch.
subpath = "reader"            # where under the published site this lands

[[libraries]]
name = "artoo-kit"
version = "0.2.0"
sha256 = "…"                  # provenance of the vendored copy

[[vendor]]
name = "mermaid"
url = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
sha256 = "…"
path = "site/lib/vendor/mermaid.min.js"
```

Top-level tables only, scalars before tables, stable key order on write —
manifests must diff cleanly in git.

### Site libraries

The tension: artifacts should be **self-contained and stable** (they keep
working when the tooling moves on) yet **easy to upgrade**. Resolution:
libraries are *vendored with provenance*. `artoo lib add artoo-kit` copies
the library's files into `site/lib/artoo-kit/` and records
name/version/hash in the manifest. `artoo lib status` detects drift (local
edits vs. upstream); `artoo lib update` re-vendors a newer version.

- artoo ships one built-in library, **artoo-kit**: DES-governed design tokens
  (light editorial default with dark as explicit opt-in), centered long-form
  prose with wider evidence regions, margin notes, tables, and a restrained
  component vocabulary. Offline system stacks expose separate serif prose and
  display roles, sans-serif UI, and monospaced numerics. The kit has no
  gradients or card/button elevation. Cards remain available for true
  navigation, not as a default information container.
- Libraries are snapshots, not live links. Changing Artoo's bundled kit does
  not rewrite an existing artifact's vendored bytes; `artoo lib update
  artoo-kit` is the explicit upgrade boundary.
- External libraries live in **their own repos/packages** and register via
  the `artoo.libraries` entry point, or are vendored from a URL with a
  pinned hash (`[[vendor]]`). Core artoo stays small; the ecosystem grows
  outside it.

### Deployment

Adapters, discovered via the `artoo.deployers` entry point group:

- **`github-pages`** — deployment intelligence lives here. It reads the
  repo's actual Pages state (`gh api repos/{owner}/{repo}/pages`) and
  handles the three real-world modes: *legacy* serving from `/docs` or
  root (copy the built site into place, commit), *workflow*
  (generate/maintain an `actions/deploy-pages` workflow that assembles
  artifacts), or *branch* (push to `gh-pages`). It refuses to guess when
  the config is ambiguous and says exactly what it found.
- **`rsync`** — ssh/rsync to named targets. Targets (host/user/path/key)
  live in `~/.config/artoo/targets.toml` or a git-ignored
  `.artoo/targets.toml` at the repo root — never in the manifest.
- **`command`** — an arbitrary publish command run with `ARTOO_SITE_DIR`,
  `ARTOO_SLUG`, etc. in the environment. The escape hatch that makes any
  bespoke pipeline work today.
- Future adapters (vercel, cloudflare) are plugins; nothing in core
  assumes a particular host.

`artoo deploy` always runs the firewall check first: notebook files,
`_`/`.`-prefixed paths, and anything outside `site/` cannot ship.

### Plugins

Three entry-point groups, all Python:

| group              | provides                          | example            |
|--------------------|-----------------------------------|--------------------|
| `artoo.generators` | `artoo generate <name> …`         | `explainer`        |
| `artoo.deployers`  | `[deploy] target = <name>`        | `github-pages`     |
| `artoo.libraries`  | vendorable asset bundles          | `artoo-kit`        |

Core ships reference implementations of each; everything else lives in
separate repos. A generator is a callable that receives a context (target
artifact, repo root, worker pool, options) and produces/updates the
artifact.

### Workers and model tiers

Generators do model work through **workers** — thin shell-outs to agent
CLIs already on the machine and already authenticated:

```toml
[workers]                      # optional overrides in artifact.toml
analysis  = "codex"            # fan-out, high-volume, cheap
synthesis = "claude"           # narrative, structure, judgment
```

- `codex` → `codex exec --sandbox read-only …` (bulk per-module analysis)
- `claude` → `claude -p … --model <tier>` (synthesis, editing, review)

Workers return text/JSON; generators validate and record results. If a
worker CLI is missing, the generator degrades explicitly (skips the stage
and says so) rather than failing the whole run. No API keys, no vendored
SDKs, no phone-home.

### Research backing

If [flip](https://github.com/lavallee/flip) is installed alongside artoo,
generators record what they learned as a flip reporter's notebook inside
the artifact: analyzed files become graded sources, generated statements
become claims with `file:line` provenance, and each run is a session. The
site is then a *render* of the notebook in flip's sense. Without flip,
generators fall back to plain markdown notes in `work/`. Either way the
material stays behind the firewall.

### Design authority and local guidance

[DES](https://github.com/lavallee/des) governs Artoo's default public-artifact
contract: start from a named reader decision and headline claim, record
supported and unsupported claims, establish vintages and denominators, and use
only valid axes of comparison. A table or figure earns its place by helping the
reader make that comparison. A clean Artoo build proves artifact integrity; it
does not confer visual or editorial acceptance.

`artoo init` records that contract in the non-deployed
`work/design-brief.md`. [Vizier](https://github.com/lavallee/vizier) is an
optional local critique and form-selection companion:

```
artoo vizier-guide "the reader's data job" --context "source and constraints" \
  --family Ranking --series-count 5 --form-count 3 --prior-count 5 \
  --no-semantic --artifact path/to/artifact
```

Artoo invokes the installed `vizier guide` executable and atomically records
its complete output and invocation metadata at `work/vizier-guidance.md` only
after a successful exit. A missing or failed executable produces an actionable
error and no partial receipt. Artoo does not import Vizier, read its private
corpus, or make a model/API call. This keeps responsibilities bounded: DES owns
design authority, Vizier offers optional implementation guidance, and Artoo
owns packaging, provenance, the firewall, and deployment.

## The explainer generator

The first serious generator: `artoo generate explainer --repo <path>`
builds a detailed multi-page explainer of a code repository.

Pipeline (each stage resumable, artifacts cached in `work/`):

1. **Inventory** (deterministic, no models) — file tree, LOC, language
   split, package/workspace layout, entry points, dependency graph
   between modules, git history shape, test topology, existing docs.
2. **Analysis fan-out** (analysis tier) — per-module briefs: what it does,
   key types/functions, invariants, dependencies, surprises. Structured
   output, validated, recorded as notebook sources/claims.
3. **Synthesis** (synthesis tier) — the narrative: what this system is,
   the reader decision, supportable headline claim, evidence limits and
   counter-reading, valid comparisons, architecture story, and reading paths.
   It selects tables or figures for those comparisons, then produces page
   plans and pages.
4. **Diagrams** — architecture/data-flow diagrams emitted as Mermaid
   source, rendered client-side by a vendored `mermaid.min.js`.
5. **Assembly** — pages composed with artoo-kit into `site/`: overview,
   architecture, module reference, data model, operations/how-to-read
   pages, with cross-links and a nav manifest.

The generated site carries a colophon: which tiers ran, when, against
which commit — an explainer is a *dated snapshot*, and says so.

## CLI surface (v0.1)

```
artoo init [path] --kind <kind> --title <t>   scaffold an artifact
artoo list [root]                             discover artifacts under a tree
artoo status [artifact]                       manifest, firewall, lib drift
artoo build [artifact]                        run build commands + checks
artoo vizier-guide <job> [--artifact <path>]  optional private guidance receipt
artoo deploy [artifact] [--dry-run]           firewall check, then adapter
artoo lib add|update|status|list              manage vendored libraries
artoo generate <generator> [opts]             run a generator plugin
artoo doctor [root]                           repo-wide coherence report
```

## Non-goals (v0.1)

- No hosted service, no accounts, no telemetry.
- No WYSIWYG editing; artifacts are files in git.
- No bundler integration; if a project needs one, its build commands can
  call it, but artoo won't manage it.
- No model API clients in core, ever.

## Success criterion for v0.1

Run the explainer against the public somm repo, land the artifact in
somm's `site/` folder, and publish it through the github-pages adapter
without disturbing somm's existing landing page.
