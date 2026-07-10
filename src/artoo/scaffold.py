"""``artoo init``: stamp a new artifact."""

from __future__ import annotations

from pathlib import Path

from . import libraries
from . import manifest as manifest_mod
from .manifest import Manifest

STARTER_PAGE = """<!doctype html>
<html lang="en">
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
<nav class="site-nav">
  <span class="brand">{title}</span>
  <button class="nav-toggle" aria-label="Menu">menu</button>
  <div class="nav-links">
    <a href="index.html">Overview</a>
  </div>
  <button data-theme-toggle class="nav-toggle" style="display:block;margin-left:auto" aria-label="Toggle theme">theme</button>
</nav>
<main class="article">
  <header class="article-header">
    <div class="article-kicker">{kind}</div>
    <h1 class="article-title">{title}</h1>
    <p class="article-dek">{description}</p>
  </header>
  <p>Start writing. The kit gives you the <code>.article</code> grid,
  margin notes, pull quotes, callouts, cards, and stats — see the
  artoo documentation for the vocabulary.</p>
  <footer class="colophon">
    Built with <a href="https://github.com/lavallee/artoo">artoo</a>.
  </footer>
</main>
<script src="lib/artoo-kit/kit.js"></script>
</body>
</html>
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

    m = manifest_mod.new(slug, title, kind=kind, description=description)
    path.mkdir(parents=True, exist_ok=True)
    m.save(path)

    site = path / m.site
    site.mkdir(exist_ok=True)
    index = site / "index.html"
    if not index.exists():
        index.write_text(
            STARTER_PAGE.format(title=title, description=description, kind=kind),
            encoding="utf-8",
        )
    libraries.add(m, "artoo-kit")

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
