"""``artoo init``: stamp a new artifact."""

from __future__ import annotations

import html
from pathlib import Path

from . import agent_guide, content as content_mod, data as data_mod, libraries
from . import manifest as manifest_mod
from .manifest import Manifest

EXPLORER_PAGE = """<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="lib/artoo-kit/favicon.svg">
<link rel="stylesheet" href="lib/artoo-kit/tokens.css">
<link rel="stylesheet" href="lib/artoo-kit/base.css">
<link rel="stylesheet" href="lib/artoo-kit/article.css">
<link rel="stylesheet" href="lib/artoo-kit/components.css">
<link rel="stylesheet" href="lib/artoo-controls/controls.css">
<style>
  .explorer-results {{ list-style: none; padding: 0; }}
  .explorer-result {{ padding: 1rem 0; border-bottom: 1px solid var(--border); }}
  .explorer-result h2 {{ margin-bottom: .25rem; }}
</style>
</head>
<body>
<header class="article-masthead">
  <a class="article-masthead__name" href="index.html">{title}</a>
  <span class="article-masthead__label">Artoo explorer</span>
</header>
<main class="page">
  <header>
    <p class="article-kicker">{kind}</p>
    <h1>{title}</h1>
    <p class="article-dek">{description}</p>
  </header>
  <div id="explorer-controls"></div>
  <ul class="explorer-results" id="explorer-results"></ul>
  <p class="controls-empty" id="explorer-empty" hidden>No results match this view. Reset a filter and try again.</p>
</main>
<script src="data/items.js"></script>
<script src="lib/artoo-controls/controls.js"></script>
<script>
(function () {{
  "use strict";
  var list = document.getElementById("explorer-results");
  var empty = document.getElementById("explorer-empty");
  function render(rows) {{
    list.textContent = "";
    empty.hidden = rows.length !== 0;
    rows.forEach(function (row) {{
      var item = document.createElement("li");
      item.className = "explorer-result";
      var heading = document.createElement("h2");
      heading.textContent = row.name;
      var detail = document.createElement("p");
      detail.textContent = row.description;
      item.appendChild(heading);
      item.appendChild(detail);
      list.appendChild(item);
    }});
  }}
  ArtooControls.create("#explorer-controls", {{
    data: window.ARTOO_DATA,
    search: {{ fields: ["name", "description"], label: "Search" }},
    filters: [{{ field: "type", label: "Type" }}],
    url: true,
    download: "{slug}.csv",
    onChange: render,
  }});
}}());
</script>
</body>
</html>
"""

ARTICLE_CONTENT = """# {title}

{description}

## What the evidence shows

State the supported finding. Keep definitions, vintages, denominators, and
source notes close to the claims they support.

## What this means for the reader

Return to the reader's decision. Distinguish what the evidence supports from
what it cannot establish.
"""

COLLECTION_INDEX = """# {title}

{description}

## Start here

Explain what this collection contains, who it is for, and the most useful
route through it.
"""

COLLECTION_EVIDENCE = """# Evidence and limits

## Sources

Name the sources, their vintages, and the claims each can carry.

## Limits

Record what the collection cannot establish and the strongest counter-reading.
"""

DECK_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="lib/artoo-deck/favicon.svg">
<link rel="stylesheet" href="lib/artoo-deck/deck.css">
<style>
  /* Your deck's own vocabulary. Keep these out of the `deck-` namespace so
     the library and your content cannot capture each other's classes. */
  .deck-root {{ --deck-print-id: "{title} \00b7"; }}
</style>
</head>
<body class="deck-root">

<header class="deck-bar">
  <span class="deck-mark">{initial}</span>
  <span class="deck-who">{title}</span>
  <span class="deck-spacer"></span>
  <button type="button" data-deck-toggle="overview" aria-pressed="false">Overview</button>
  <button type="button" data-deck-toggle="notes" aria-pressed="false">Notes</button>
  <button type="button" data-deck-toggle="help">?</button>
  <nav class="deck-pager" aria-label="Slide navigation">
    <button type="button" data-deck-prev aria-label="Previous slide">&#8249;</button>
    <span class="deck-counter" data-deck-counter>1 / 1</span>
    <button type="button" data-deck-next aria-label="Next slide">&#8250;</button>
  </nav>
</header>
<div class="deck-progress"><i data-deck-progress style="width:0%"></i></div>
<nav class="deck-pager-m" aria-label="Slide navigation">
  <button type="button" data-deck-prev aria-label="Previous slide">&#8249;</button>
  <span class="deck-counter" data-deck-counter>1 / 1</span>
  <button type="button" data-deck-next aria-label="Next slide">&#8250;</button>
</nav>

<main class="deck-stage" data-deck>

<section class="deck-slide" data-act="Opening" data-short="Title">
  <div class="deck-inner">
    <p class="deck-eyebrow">{kind}</p>
    <h1>{title}</h1>
    <p class="deck-lede">{description}</p>
    <aside class="deck-notes"><b>Speaker note</b>
      <p>Say what decision this deck helps the room make, and how long it will
      take. Notes are hidden until toggled, and they print with the slide.</p>
    </aside>
  </div>
</section>

<section class="deck-slide" data-act="Evidence" data-short="The claim">
  <div class="deck-inner">
    <p class="deck-eyebrow">The claim</p>
    <h2>State the single claim the evidence can carry</h2>
    <div class="deck-stat-row">
      <div class="deck-stat"><b>00</b><span>the number that carries the claim</span></div>
      <div class="deck-stat"><b>00</b><span>its denominator</span></div>
    </div>
    <p>Develop the argument in one screen. A slide that needs scrolling is
    two slides.</p>
    <div class="deck-callout"><p>Use a callout for the sentence you want
    repeated back to you.</p></div>
    <aside class="deck-notes"><b>Speaker note</b>
      <p>Name the vintage and the denominator out loud; they belong on the
      slide too.</p>
    </aside>
  </div>
</section>

<section class="deck-slide" data-act="Evidence" data-short="Limits">
  <div class="deck-inner">
    <p class="deck-eyebrow">Limits</p>
    <h2>What the evidence cannot establish</h2>
    <div class="deck-grid two">
      <div class="deck-cell"><b>Supported</b><p>What the measurement does show.</p></div>
      <div class="deck-cell"><b>Not supported</b><p>The strongest counter-reading, stated before anyone asks.</p></div>
    </div>
    <aside class="deck-notes"><b>Speaker note</b>
      <p>Saying the limit first is what earns the rest of the deck.</p>
    </aside>
  </div>
</section>

</main>

<div class="deck-overview" data-deck-overview></div>

<div class="deck-help" data-deck-help>
  <div class="deck-help-card">
    <h3>Keyboard</h3>
    <dl>
      <dt>&rarr; &darr; space</dt><dd>Next slide</dd>
      <dt>&larr; &uarr;</dt><dd>Previous slide</dd>
      <dt>Home / End</dt><dd>First / last slide</dd>
      <dt>1&ndash;9</dt><dd>Jump to slide</dd>
      <dt>o</dt><dd>Overview</dd>
      <dt>s</dt><dd>Speaker notes</dd>
      <dt>f</dt><dd>Fullscreen</dd>
      <dt>p</dt><dd>Print / export PDF</dd>
      <dt>?</dt><dd>This panel</dd>
      <dt>Esc</dt><dd>Close overlays</dd>
    </dl>
  </div>
</div>

<script src="lib/artoo-deck/deck.js"></script>
</body>
</html>
"""

ARTIFACT_BRIEF = """# Artifact brief

Private working document. Artoo keeps this file outside `site/`; it is not deployed.

## Reader decision

Who is the named reader, and what decision should this artifact help them make?

## Headline claim

What is the single claim the evidence can carry?

## Supported claims

-

## Unsupported claims and counter-reading

- What can the evidence not establish?
- What is the strongest plausible counter-reading?

## Data vintages and denominators

- Source / vintage / denominator / unit:

## Licit comparisons

- Which axes of comparison are valid, and why?
- Which comparisons are invalid or misleading?

## Selected forms

- Presentation form / reader task served / reason this form helps:
- Table or figure / comparison served / reason this form helps:

## Presentation intent

- Desired reading experience:
- Existing artifact or publication worth learning from:

## Anti-reference

- Example to avoid / failure mode:

## Proof required

- Factual proof:
- Visual and editorial proof:
- Offline and firewall proof:
"""


def init_artifact(
    path: Path,
    *,
    slug: str = "",
    title: str = "",
    kind: str = "report",
    form: str = "",
    description: str = "",
    with_notebook: bool = False,
) -> Manifest:
    """Create an artifact at ``path``: manifest, starter site, vendored kit."""
    path = path.resolve()
    if (path / manifest_mod.MANIFEST_NAME).exists():
        raise FileExistsError(f"{path} already holds an artifact")
    slug = slug or path.name
    title = title or slug.replace("-", " ").replace("_", " ")
    deck = description or (
        "State why the headline matters, the evidence it rests on, and its principal limit."
    )

    m = manifest_mod.new(slug, title, kind=kind, description=description, form=form)
    m.form = m.effective_form
    if m.form == "article":
        m.content_source = "content.md"
    elif m.form == "collection":
        m.content_pages = "content"
        m.content_order = ["index.md", "evidence.md"]
    elif m.form == "explorer":
        m.data_packs = [
            {
                "source": "work/items.json",
                "path": "data/items.json",
                "script": "data/items.js",
                "global": "ARTOO_DATA",
            }
        ]
    path.mkdir(parents=True, exist_ok=True)
    m.save(path)

    site = path / m.site
    site.mkdir(exist_ok=True)
    work = path / "work"
    work.mkdir(exist_ok=True)
    (work / "artifact-brief.md").write_text(ARTIFACT_BRIEF, encoding="utf-8")

    index = site / "index.html"
    values = {
        "title": html.escape(title),
        "description": html.escape(deck),
        "kind": html.escape(kind),
        "created": m.created,
        "initial": html.escape(title[:1].upper() or "A"),
        "slug": html.escape(slug),
    }
    if m.form == "deck":
        index.write_text(DECK_PAGE.format(**values), encoding="utf-8")
        libraries.add(m, "artoo-deck")
    elif m.form == "explorer":
        index.write_text(EXPLORER_PAGE.format(**values), encoding="utf-8")
        libraries.add(m, "artoo-kit")
        libraries.add(m, "artoo-controls")
        (work / "items.json").write_text(
            "[\n"
            '  {"name": "First item", "type": "Example", '
            '"description": "Replace work/items.json with the rows readers explore."},\n'
            '  {"name": "Second item", "type": "Reference", '
            '"description": "Search, filter, URL state, counts, reset, and CSV are wired."}\n'
            "]\n",
            encoding="utf-8",
        )
        data_mod.pack(m)
    elif m.form == "collection":
        libraries.add(m, "artoo-kit")
        pages = path / "content"
        pages.mkdir(exist_ok=True)
        (pages / "index.md").write_text(
            COLLECTION_INDEX.format(title=title, description=deck), encoding="utf-8"
        )
        (pages / "evidence.md").write_text(COLLECTION_EVIDENCE, encoding="utf-8")
        content_mod.render(m)
    else:
        libraries.add(m, "artoo-kit")
        (path / "content.md").write_text(
            ARTICLE_CONTENT.format(title=title, description=deck), encoding="utf-8"
        )
        content_mod.render(m)

    if with_notebook:
        _init_notebook(m)

    # Last, so the guide describes the artifact as finished — including the
    # notebook binding. Whoever authors this artifact next arrives holding
    # only this directory; the guide is what they read instead of inferring
    # the layout vocabulary from the vendored stylesheets.
    agent_guide.write(m)
    return m


def _init_notebook(m: Manifest) -> None:
    """Prefer a flip reporter's notebook; fall back to a plain notebook.md."""
    nb_dir = m.dir / "notebook"
    try:
        from flip import scaffold as flip_scaffold  # type: ignore[import-not-found]

        flip_scaffold.create_notebook(
            m.dir, "notebook", kind="scout", title=m.title, visibility="private"
        )
    except Exception:
        nb_dir.mkdir(exist_ok=True)
        (nb_dir / "notebook.md").write_text(
            f"# {m.title} — notebook\n\n"
            "Research backing for this artifact. Never deployed.\n\n"
            "## Sources\n\n## Claims\n\n## Decisions\n",
            encoding="utf-8",
        )
    m.notebook = "notebook"
    m.save()
