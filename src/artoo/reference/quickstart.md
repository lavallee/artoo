# Quickstart

artoo builds **artifacts**: self-contained HTML mini-sites that pair a piece of
presentation with the research backing it. An artifact is a directory holding
an `artifact.toml`, and it lives inside whatever repo owns the subject. One
repo can hold many.

## The golden path

```bash
artoo init docs/spending-report --title "Where the money went"
# …author content.md; use raw site/index.html when the form needs it…
artoo status docs/spending-report     # manifest health, firewall, library drift
artoo build  docs/spending-report     # render, pack data, verify, stamp `updated`
artoo verify docs/spending-report     # links, assets, anchors, offline dependencies
artoo deploy docs/spending-report     # firewall-stage, then publish
```

`artoo init` writes a concise `AGENTS.md` for automatic context and an
`ARTOO_REFERENCE.md` carrying the complete layout vocabulary generated from
the libraries that artifact actually vendored. Open the latter only when the
work needs the deeper contract.

## What init creates

```
docs/spending-report/
  artifact.toml           the manifest — source of truth
  AGENTS.md               concise working rules (generated; safe to extend)
  ARTOO_REFERENCE.md      full vendored vocabulary, on demand
  content.md              article source (omit [content] to own raw site/ HTML)
  site/
    index.html            the starter page
    lib/artoo-kit/        vendored, hash-pinned styling
  work/
    artifact-brief.md     private: reader decision, claim, limits, intent
```

Only `site/` is publishable. See `artoo docs firewall`.

## Choosing a kind and form

`kind` describes the subject; `form` describes how a reader works with it.
Artoo infers a useful default, and `--form` overrides it independently.

```bash
artoo init talks/q3 --kind presentation --title "Q3 review"
artoo init data/places --kind report --form explorer --title "Compare places"
```

Kinds: `explainer`, `report`, `reference-guide`, `research-review`,
`walkthrough`, `presentation`, `case-study`, `explorer`, `note`.

Forms: `article`, `explorer`, `collection`, `deck`. See `artoo docs forms`.

## Authoring rules that matter

1. **Use the vocabulary the artifact vendored.** `ARTOO_REFERENCE.md` and
   `artoo docs artoo-kit` list every class, with its role. `artoo build` fails on a
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
