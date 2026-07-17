"""``artoo init``: stamp a new artifact."""

from __future__ import annotations

import html
from pathlib import Path

from . import libraries
from . import manifest as manifest_mod
from .manifest import Manifest

STARTER_PAGE = """<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
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
    if not index.exists():
        index.write_text(
            STARTER_PAGE.format(
                title=html.escape(title),
                description=html.escape(deck),
                kind=html.escape(kind),
                created=m.created,
            ),
            encoding="utf-8",
        )
    libraries.add(m, "artoo-kit")

    work = path / "work"
    work.mkdir(exist_ok=True)
    (work / "design-brief.md").write_text(DESIGN_BRIEF, encoding="utf-8")

    if with_notebook:
        _init_notebook(m)
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
