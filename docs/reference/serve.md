# Serving an artifact, and where saved state goes

Most artifacts are finished the moment they render, and `file://` is the right
way to read them. Explorers are the exception. A page whose value is the
configuration a reader arrived at — a set of weights, a chosen comparison, a
saved view — is only useful the second time if that configuration survives.

```bash
artoo serve site/my-explorer          # http://127.0.0.1:8765/
artoo serve site/my-explorer --open --port 9000
```

## What it serves

The **firewall-staged** site, not `site/` itself. So the server shows exactly
what a deploy would show: a withheld file is *absent*, not merely unlinked, and
a page that only works because it reached a private working file fails here
rather than after publication.

Loopback only, no authentication. This is a working surface, not a host.

## The state store

One API lives under `/_artoo/state`, and it reads and writes named JSON
documents into the artifact's own `state/` directory:

| request | effect |
|---------|--------|
| `GET /_artoo/state/<collection>` | list documents: name, updated, bytes |
| `GET /_artoo/state/<collection>/<name>` | read one document |
| `PUT /_artoo/state/<collection>/<name>` | write it, body `{"document": …}` |
| `DELETE /_artoo/state/<collection>/<name>` | remove it |

`state/presets/means-heavy.json` is a real file next to the work, committed
with it and readable in a diff. Browser storage is the cheap alternative and
the wrong one: per-browser, invisible to the repo, lost on a profile reset,
and impossible for a second person to read.

**`state/` is a sibling of `site/`.** That is the whole point of putting it
there — the firewall only ever ships from the site root, so nothing a reader
saves can reach a publish by accident.

Writes are atomic (temp file, then rename), so a crashed or concurrent save
cannot leave a half-parsed preset the page will then refuse to load.

## Two rules on the write path

Collection and document names must match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`.
The path is built from a validated name and never from raw request text, so
`..` and absolute paths cannot appear. Bodies are capped at 4 MB; a saved view
is small, and anything larger is a mistake worth surfacing.

## From the page

`ArtooStore` in artoo-kit is the client:

```js
const presets = ArtooStore.open("presets");
await presets.save("means-heavy", weights);   // → state/presets/means-heavy.json
await presets.list();                          // [{name, updated, bytes}, …]
await presets.load("means-heavy");
await presets.remove("means-heavy");
```

Opened from `file://` or a plain static host there is no server to write to, so
the store falls back to `localStorage` and reports `durable === false`. Print
`presets.describe()` in the interface rather than let a reader believe a save
reached disk when it did not.
