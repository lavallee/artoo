# Serving an artifact, and where saved state goes

`artoo serve path/to/artifact --open` serves the artifact's `site/` through
its publication firewall, on loopback by default. It is a working surface,
not an authenticated public host. Private files outside `site/` remain private.

## The shared state contract

The protocol-2 API stores named JSON documents under the owning artifact's
`state/` directory, outside `site/`. A compatible reader such as Dirk can mount
the same API below the artifact URL. Enable only specifically declared state
collections with `[state]` and `collections = ["feedback"]` in `artifact.toml`; never accept
a filesystem path from page JavaScript. Hosting or authentication changes are
separate deployment decisions, not implicit consequences of authoring a page.

Artifacts on the same origin retain that origin's existing trust boundary.
Collection opt-in bounds filesystem writes; it does not sandbox mutually
untrusted pages on one origin. Serve only trusted artifacts within the existing
authenticated access boundary, and do not expand access to enable saves.

| Request below the artifact root | Effect |
|---|---|
| `GET _artoo/state/<collection>` | capability response `protocol: 2`, `durable: true`, entries |
| `GET _artoo/state/<collection>/<name>` | document envelope including `revision`; 404 if absent |
| `PUT _artoo/state/<collection>/<name>` | JSON `{document, expected_revision}` |
| `DELETE _artoo/state/<collection>/<name>` | JSON `{expected_revision}` |

A new document uses `expected_revision: null`; an update uses the exact revision
last read. A stale revision returns conflict (409), never last-writer-wins.
Hosts may deliberately deny DELETE; surface that refusal without fallback.
Collection/document names match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` and the service
bounds request size. Atomic replacement prevents partial documents; revision
checks protect concurrent edits. A successful save confirms a disk write.
**It does not commit or push Git.** Review and commit only the intended artifact
state JSON files separately. Ignore `state/**/.lock` and `state/**/.pending-*`
(the latter can remain after an interrupted process); never stage the whole repository to capture feedback.

## Authoring with ArtooStore

Upgrade the pinned kit explicitly with `artoo lib update`; existing vendored
copies are not silently rewritten. Load the kit's `store.js` normally from
`lib/artoo-kit/store.js`. It derives the artifact root from that script URL,
including when the current page is nested. An explicit same-origin `base` option
or `<meta name="artoo-state-base" content="…">` overrides the endpoint.

```js
const store = ArtooStore.open("feedback");
// Keep editing disabled until the shared document has been read.
let document = await store.load("review"); // document or null; remembers revision
// Render the shared document and any pending/browser copy for comparison.
const browserCopy = store.inspectLocal("review");
const pending = store.inspectPending("review");
// Enable editing only when unresolved pending data has been handled.
await store.save("review", editedDocument);
status.textContent = store.describe();
```

Serialize saves and catch every failure. Display a saving state before awaiting,
then display `describe()` or equivalent only after the response. Disable edits
until load finishes, preserve the visible edit on errors, and provide a retry or
comparison action. `store.status` distinguishes `unloaded`, `loaded`, `saving`,
`saved`, `conflict`, `unsaved`, `unavailable`, and `browser-only`. `durable` means
the protocol was discovered, not that the latest edit succeeded.

HTTP service errors never silently switch to browser-only saves. Explicit
`ArtooStore.open("feedback", {localOnly: true})` or a `file://` page uses the
legacy browser store, and must visibly say **browser only**. A protocol-1 server
must be upgraded; its successful response cannot establish conflict safety.

## Browser import and interrupted saves

The legacy `artoo:state:<collection>:<name>` browser key is preserved. Inspect it
with `inspectLocal(name)`, show its content alongside a fresh `load(name)`, and
ask the reader to choose/merge differences. Only after that explicit choice:

```js
await store.importLocal("review", {confirm: true, document: reviewedMergedDocument});
```

This saves against the revision remembered by `load` and leaves the original
browser copy intact. Never automatically replace shared feedback with an old
browser copy. Different browsers may contain different legacy copies.

Before a network write, the client retains a separate browser pending envelope
containing the payload and its original expected revision. Each operation has
its own journal ID, so one browser tab cannot clear another tab's failed save. If browser storage
refuses that recovery copy, the write is refused. `inspectPending(name)` exposes
it after a reload; `listPending(name)` returns all outstanding operations.
Pass a `pending_id` to `inspectPending(name, id)`, `recoverPending(name, id)`,
or `discardPending(name, id)` when choosing among several.
`resolvePending` accepts the selected `pending_id` in its options.
`recoverPending(name)` retries that exact revision, after
loading shared state, so recovery cannot overwrite a newer edit. A lost response
may mean the disk write already succeeded: compare the pending and shared copies
before acting. Recovery may correctly conflict in this case.

A pending edit blocks a new save until the reader has recovered or explicitly
resolved it. For a manual merge, retain both copies in the UI, load shared state,
and call `resolvePending(name, {confirm: true, document: reviewedMergedDocument})`
after the reader approves. It writes a separate recovery envelope before the network request, retaining
the original until the merge is acknowledged, avoiding a discard-then-save crash gap.
`discardPending(name)` is available only for an explicit decision to abandon an
edit; never use it automatically on load or on a failed save. Neither action
removes the legacy browser source.

Test a fresh second browser context, reload, concurrent edits, offline failure,
interrupted acknowledgement, and the import comparison flow. A same-session
localStorage read does not demonstrate shared persistence. Keep tests and
captures inside the artifact's private working area, and never put saved reader
feedback into the public `site/` tree.
