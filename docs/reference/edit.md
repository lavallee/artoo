# Editing pages in place, and the source map

`artoo edit <artifact>` opens every page the artifact renders for editing in the
browser: text in place with a review of each change and revert, a Markdown source
view, comments, section status, and a rebuild after every save. The editor is
Copycat, a separate local tool found through
`--copycat DIR` or `COPYCAT_HOME`; Artoo makes no edits itself and runs without it.

```toml
[content]
pages = "content"                 # or source = "content.md"
sourcemap = true                  # required by `artoo edit`

[edit]
comments = "edit/comments.json"   # optional; comments anchored to source spans
status = "edit/status.json"       # optional; draft, in review, locked per file
# config = "editor/copycat.json"  # optional; your own editor config instead
```

```bash
artoo edit .                       # build, then serve with the editor on 127.0.0.1:8916
artoo edit . --share-origin https://host.example   # also admit one authenticated https origin
artoo edit . --agent codex --agent-bin /abs/path/codex
artoo edit . --print-config        # write and show the generated editor config
```

The editor binds to loopback. `--share-origin` admits exactly one https origin,
which must already be behind authentication; it is not a way to publish. Saves
write the source files, never `site/`, and never commit.

Without `[edit] config`, Artoo writes `work/editor/copycat.json`: every Markdown
file the source map names, the manifest title, the `[edit]` files, and
`artoo build --no-browser .` as the rebuild. Registered files are the editor's
write boundary, so an artifact with text in other files (figure text from
generated JSON, say) keeps a config of its own and names it in `[edit] config`.

## The source map

With `sourcemap = true`, each block a build renders from Markdown (heading,
paragraph, list item, table, quote, image figure, and the page's title, dek and
masthead) carries an opaque `data-artoo-src` id, and the build writes
`work/artoo-sourcemap.json` (`artoo-sourcemap/1`):

```json
{
  "contract": "artoo-sourcemap/1",
  "files": {"chapters/03.md": "<sha256 at build time>"},
  "pages": {
    "03.html": {
      "source": "work/pages/03.md",
      "evidence": ["Q20"],
      "blocks": [
        {"id": "a1", "kind": "title", "file": "chapters/03.md", "lines": [1, 1]},
        {"id": "a3", "kind": "paragraph", "file": "chapters/03.md", "lines": [3, 4]},
        {"id": null, "kind": "block:html", "file": "specs/curve.json", "lines": null,
         "derives": ["work/receipt.json"]}
      ]
    }
  }
}
```

An editor maps each block to its file and lines instead of matching rendered
text back to Markdown, so repeated text is editable and a renderer change cannot
silently mis-map. A file whose hash differs from `files` has changed since the
build; that part of the map is stale until the next build. Ids carry no paths,
and the map stays in `work/`, which never publishes. A `:::` block renders raw
HTML and cannot carry an id; it is listed with `id: null`.

## Pages assembled from other files

A build command that writes the Markdown Artoo renders (a chapter per page, with
figures rendered from data) keeps the map true with origin comments, one per
line, which never render:

```markdown
<!-- artoo:source chapters/03.md:1 derives=work/v3/timing.json -->
# The chapter's finding
<!-- artoo:source specs/curve.json derives=work/v3/timing.json -->
::: html
<figure>…</figure>
:::
<!-- artoo:source chapters/03.md:5 -->
The paragraph after the figure.
<!-- artoo:source - -->
```

`FILE:LINE` says the next line is that file's line LINE, and so on; a file
with no line names where a generated block came from; `derives=` lists the files
its numbers come from (used for evidence, `artoo docs provenance`); `-` marks
generated lines with no source. Put the comment directly above the line it
describes. Leading comments may precede front matter.
