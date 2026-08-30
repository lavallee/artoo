# Evidence and the research roundtrip

An artifact can project provider-neutral evidence directly, or attach a
[flip](https://github.com/lavallee/flip) notebook and use Flip as an adapter.
Either route lands the same browser-facing provenance files, so presentation
does not depend on a particular research system.

## Provider-neutral evidence

```toml
[evidence]
source = "work/evidence.json"
```

The source uses `artoo-evidence/1`:

```json
{
  "contract": "artoo-evidence/1",
  "sources": [{"id": "A1", "title": "Primary dataset", "grade": "A"}],
  "claims": [{"id": "C1", "text": "The supported claim", "sources": ["A1"]}]
}
```

Source ids and titles, claim ids and text, and claim-to-source references are
validated. A declared source that is missing or invalid fails the build.

## Flip adapter

When `[evidence]` is absent, an artifact can attach a Flip notebook. Artoo reads
it back out at build time so the published page carries its own lineage.

The Flip route no-ops cleanly with no Flip installed. Artoo core has no hard
dependency on it; the integration is a soft import, discovered on `PATH` or
pinned with `ARTOO_FLIP_BIN`.

## Attaching a notebook

```toml
[research]
notebook = "notebook"
```

`artoo init --notebook` scaffolds one. The path is relative and may point
outside the artifact — the read-direction generator renders a report *from* a
canonical notebook that is the source of truth elsewhere.

## The projection

```bash
artoo provenance <artifact>   # flip export json → site/data/provenance.json
artoo status     <artifact>   # …and reports whether the render is stale
```

`artoo build` refreshes either projection automatically and records a Flip notebook
`uid` + `updated` in the manifest as the render vintage. flip does the
policy filtering; artoo passes `--include-private` only when the manifest sets
`[research] include_private = true`.

A Flip refusal here is never a build failure — no Flip, no notebook, or a
visibility policy that declines all read as a note.

## Rendering the panel

The kit ships the panel; both evidence routes use the same three lines:

```html
<section class="provenance article-breakout" data-artoo-provenance></section>

<script src="data/provenance.js"></script>
<script src="lib/artoo-kit/provenance.js"></script>
```

`data/provenance.js` sets a global so the panel hydrates from `file://`, where
a bare `fetch()` of a sibling JSON is blocked. Both files are written by
`artoo provenance`. With no projection present the panel hides itself and the
page reads exactly as authored, so wiring it early is safe.

Bracketed ids in prose — `[C7]`, `[A3]` — that the projection knows become
stable anchors linking to their panel entry. Ids it does not know are left
alone, and text inside `<code>`/`<pre>` is never rewritten.

## The structural verbs

The loop runs both ways:

```bash
# Read: render a report FROM a canonical notebook.
artoo generate notebook-report --notebook path/to/notebook --out site/report

# Reverse: route a correction back INTO the notebook. Never edits site/.
artoo feedback site/report "C7 overstates the effect" --claim C7
```

## The publish gate

`artoo deploy` runs `flip doctor` on the attached notebook first and refuses to
publish on ERROR-level findings. `--allow-doctor-errors` overrides it
deliberately.
