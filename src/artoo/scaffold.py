"""``artoo init``: stamp a new artifact."""

from __future__ import annotations

import html
from pathlib import Path

from . import agent_guide, libraries
from . import manifest as manifest_mod
from .manifest import Manifest

STARTER_PAGE = """<!doctype html>
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
</head>
<body>
<header class="article-masthead">
  <a class="article-masthead__name" href="index.html">{title}</a>
  <span class="article-masthead__label">DES public artifact</span>
</header>
<main class="article">
  <header class="article-header">
    <div class="article-kicker">{kind}</div>
    <h1 class="article-title">{title}</h1>
    <p class="article-dek">{description}</p>
    <p class="article-byline">Published <time datetime="{created}">{created}</time></p>
  </header>
  <p class="article-lede">Begin with the decision this artifact helps a named
  reader make. State the headline claim, then show the evidence and its limits
  in a narrative sequence.</p>
  <h2>What the evidence shows</h2>
  <p>Develop the argument in centered prose. Keep definitions and source
  provenance close to the claims they support.</p>
  <figure class="article-figure">
    <table>
      <thead>
        <tr><th>Comparison</th><th>Evidence</th><th>Limit</th></tr>
      </thead>
      <tbody>
        <tr><td>Name the valid axis</td><td>Report the supported finding</td><td>Record the counter-reading</td></tr>
      </tbody>
    </table>
    <figcaption>Use a wider table or figure only when it helps the reader make
    a valid comparison. Include vintages, denominators, and a source note.</figcaption>
  </figure>
  <h2>What this means for the reader</h2>
  <p>Return to the reader's decision and distinguish what the evidence supports
  from what it cannot establish.</p>
  <footer class="colophon">
    Built with <a href="https://github.com/lavallee/artoo">artoo</a>.
  </footer>
</main>
</body>
</html>
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

DESIGN_BRIEF = """# Design brief

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

- Table or figure / comparison served / reason this form helps:

## Closest DES reference

- Reference / relevant principle:

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

    m = manifest_mod.new(slug, title, kind=kind, description=description)
    path.mkdir(parents=True, exist_ok=True)
    m.save(path)

    site = path / m.site
    site.mkdir(exist_ok=True)
    index = site / "index.html"
    # Kind-aware scaffolding. A presentation is a different reading mode, not a
    # styled article: one frame at a time, an act structure, a landscape page.
    # It gets the deck skeleton and the deck library.
    starter, lib = (DECK_PAGE, "artoo-deck") if kind == "presentation" else (STARTER_PAGE, "artoo-kit")
    if not index.exists():
        index.write_text(
            starter.format(
                title=html.escape(title),
                description=html.escape(deck),
                kind=html.escape(kind),
                created=m.created,
                initial=html.escape(title[:1].upper() or "A"),
            ),
            encoding="utf-8",
        )
    libraries.add(m, lib)

    work = path / "work"
    work.mkdir(exist_ok=True)
    (work / "design-brief.md").write_text(DESIGN_BRIEF, encoding="utf-8")

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
