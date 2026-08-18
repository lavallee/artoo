# Quickstart

artoo builds **artifacts**: self-contained HTML mini-sites that pair a piece of
presentation with the research backing it. An artifact is a directory holding
an `artifact.toml`, and it lives inside whatever repo owns the subject. One
repo can hold many.

## The golden path

```bash
artoo init docs/spending-report --title "Where the money went"
# …author site/index.html…
artoo status docs/spending-report     # manifest health, firewall, library drift
artoo build  docs/spending-report     # refresh inputs, verify, stamp `updated`
artoo deploy docs/spending-report     # firewall-stage, then publish
```

`artoo init` writes an `AGENTS.md` into the new artifact carrying the layout
contract for whatever library it vendored. Read that file before writing
markup; it is generated from the stylesheets actually vendored into *that*
artifact, so it cannot describe a class that is not there.

## What init creates

```
docs/spending-report/
  artifact.toml           the manifest — source of truth
  AGENTS.md               the usage contract (generated; safe to extend)
  site/
    index.html            the starter page
    lib/artoo-kit/        vendored, hash-pinned styling
  work/
    design-brief.md       private: reader decision, headline claim, limits
```

Only `site/` is publishable. See `artoo docs firewall`.

## Choosing a kind

`--kind` is not cosmetic. `presentation` scaffolds a deck — slides, acts,
speaker notes, landscape print — and vendors `artoo-deck` instead of
`artoo-kit`. Everything else scaffolds a long-form article page.

```bash
artoo init talks/q3 --kind presentation --title "Q3 review"
```

Kinds: `explainer`, `report`, `reference-guide`, `research-review`,
`walkthrough`, `presentation`, `case-study`, `explorer`, `note`.

## Authoring rules that matter

1. **Use the vocabulary the artifact vendored.** `artoo docs artoo-kit` (or
   `artoo-deck`) lists every class, with its role. `artoo build` fails on a
   class invented inside a library's namespace, and names the nearest real
   one.
2. **Never reach for a CDN.** An artifact must render from a `file://` URL.
   Vendor a runtime with `artoo lib vendor <name> <url>` and it is recorded
   with a pinned hash.
3. **Style SVG with CSS, not presentation attributes.** `fill="var(--chart-1)"`
   does not resolve. Give the shape a class and set `fill` in a `<style>`
   block.
4. **Put research in `work/` or `notebook/`.** Both sit beside the
   presentation and neither can ship.

## Doing it in bulk

```bash
artoo list  .            # every artifact under a root (--json for machines)
artoo doctor .           # repo-wide coherence: manifests, firewall, drift
```
