# artifact.toml

The manifest is the source of truth for an artifact: listings, deploy routing,
library provenance, and render vintage all derive from it. artoo writes it
deterministically — fixed key order, scalars before tables — so it diffs
cleanly.

```toml
[artifact]
slug = "spending-report"          # [a-zA-Z0-9-_], required
title = "Where the money went"    # required
description = "…"
kind = "report"                   # see the kinds list below
status = "draft"                  # draft | building | live | archived
created = "2026-08-18"
updated = "2026-08-18"            # stamped by a successful `artoo build`

[build]
site = "site"                     # the publishable root, relative, inside the artifact
commands = ["make data"]          # refresh generated inputs; run with the artifact dir as cwd

[research]
notebook = "notebook"             # relative path to a flip notebook; may escape with ../
include_private = false           # opt in to projecting a non-public notebook
rendered_uid = ""                 # notebook vintage the site was last rendered from
rendered_updated = ""

[deploy]
target = "github-pages"           # github-pages | rsync | command
# adapter-specific keys live here too

[workers]
# generator model tiers, e.g. cheap = "codex", strong = "claude"

[[libraries]]                     # written by `artoo lib add`; do not hand-edit
name = "artoo-kit"
version = "0.3.0"
sha256 = "…"                      # content hash of the vendored tree

[[vendor]]                        # written by `artoo lib vendor`
name = "mermaid"
url = "https://…"
sha256 = "…"
path = "site/lib/vendor/mermaid.min.js"
```

**Kinds**: `explainer`, `report`, `reference-guide`, `research-review`,
`walkthrough`, `presentation`, `case-study`, `explorer`, `note`.

## Rules the validator enforces

- `slug` and `title` are required; `kind` and `status` must be known values.
- `build.site` is relative and inside the artifact — no `..`, no absolute path.
- `research.notebook` is relative. It **may** escape the artifact with `..`:
  a report can be rendered from a canonical notebook that lives elsewhere and
  is the source of truth. It must never overlap `build.site`.
- `[[libraries]]` and `[[vendor]]` entries carry their hashes. Editing a
  vendored file by hand shows up as `modified` in `artoo status`; that is
  the intended signal, not a failure.

Check any artifact with `artoo status <path>`, or a whole repo with
`artoo doctor .`.
