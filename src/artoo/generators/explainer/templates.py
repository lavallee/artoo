"""Page assembly: wrap generated fragments in the site shell."""

from __future__ import annotations

import html

PAGE_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {site_title}</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="lib/artoo-kit/tokens.css">
<link rel="stylesheet" href="lib/artoo-kit/base.css">
<link rel="stylesheet" href="lib/artoo-kit/article.css">
<link rel="stylesheet" href="lib/artoo-kit/components.css">
</head>
<body>
<nav class="site-nav">
  <span class="brand">{site_title}</span>
  <button class="nav-toggle" aria-label="Menu">menu</button>
  <div class="nav-links">
{nav_links}
  </div>
  <button data-theme-toggle class="nav-toggle" style="display:block;margin-left:auto" aria-label="Toggle theme">theme</button>
</nav>
<main class="article">
{body}
<footer class="colophon article-full" style="margin-left:var(--sp-6);margin-right:var(--sp-6)">
{colophon}
</footer>
</main>
{mermaid_tag}<script src="lib/artoo-kit/kit.js"></script>
</body>
</html>
"""


def nav_links(pages: list[dict], current_slug: str) -> str:
    lines = []
    for page in pages:
        current = ' aria-current="page"' if page["slug"] == current_slug else ""
        lines.append(
            f'    <a href="{page["slug"]}.html"{current}>{html.escape(page["title"])}</a>'
        )
    return "\n".join(lines)


def colophon(meta: dict) -> str:
    """The honesty block: an explainer is a dated snapshot and says so."""
    parts = [
        f"Generated {meta['date']} by "
        '<a href="https://github.com/lavallee/artoo">artoo</a> '
        f"v{meta['artoo_version']} (explainer generator)."
    ]
    if meta.get("commit"):
        parts.append(f"Describes <code>{meta['repo_name']}</code> at commit <code>{meta['commit']}</code>.")
    if meta.get("workers"):
        parts.append(f"Workers: {html.escape(meta['workers'])}.")
    parts.append("Machine-written from a deterministic inventory plus per-area "
                 "code analysis; verify load-bearing claims against the source.")
    return "  " + "<br>\n  ".join(parts)


def render_page(
    *, page: dict, pages: list[dict], site_title: str, body: str,
    meta: dict, mermaid_src: str = "",
) -> str:
    mermaid_tag = f'<script src="{mermaid_src}"></script>\n' if mermaid_src else ""
    return PAGE_SHELL.format(
        title=html.escape(page["title"]),
        site_title=html.escape(site_title),
        description=html.escape(page.get("purpose", ""))[:300],
        nav_links=nav_links(pages, page["slug"]),
        body=body,
        colophon=colophon(meta),
        mermaid_tag=mermaid_tag,
    )
