"""Page assembly for the notebook-report generator.

Reuses the explainer's page shell, provenance wiring, and nav so a report page
gets the same kit chrome — the provenance panel, claim anchors, favicon, and
theme/nav behaviour — for free. Only the colophon differs: a report is a *render*
of a canonical flip notebook, and says so loudly.
"""

from __future__ import annotations

import html

from ..explainer.templates import (
    PAGE_SHELL,
    PROVENANCE_PANEL,
    PROVENANCE_SCRIPTS,
    nav_links,
)


def colophon(meta: dict) -> str:
    """The honesty block for a notebook render.

    Names the notebook vintage and states the regeneration contract in plain
    terms: this page is owned by the generator, hand edits do not survive, and
    corrections belong in the notebook (flip principle 8).
    """
    parts = [
        f"Generated {meta['date']} by "
        '<a href="https://github.com/lavallee/artoo">artoo</a> '
        f"v{meta['artoo_version']} (notebook-report generator)."
    ]
    if meta.get("notebook_uid") or meta.get("notebook_updated"):
        vintage = " ".join(
            bit
            for bit in (
                f"notebook <code>{html.escape(meta.get('notebook_uid', ''))}</code>"
                if meta.get("notebook_uid")
                else "",
                f"updated {html.escape(meta.get('notebook_updated', ''))}"
                if meta.get("notebook_updated")
                else "",
            )
            if bit
        )
        parts.append(f"Rendered from {vintage}.")
    if meta.get("source") == "draft":
        parts.append("Body rendered from the notebook's current draft.")
    elif meta.get("source") == "skeleton":
        parts.append(
            "No draft was present, so the body is an honest structured skeleton "
            "projected from the notebook — not authored prose."
        )
    # The regeneration contract, stated loudly (flip principle 8 / SPEC §11).
    parts.append(
        "<strong>This page is a render. Re-running "
        "<code>artoo generate notebook-report</code> regenerates it in place and "
        "overwrites any edits — do not hand-edit it. Fixes belong in the "
        "notebook (or use <code>artoo feedback</code>), then regenerate.</strong>"
    )
    parts.append(
        "See the provenance panel for sources and claims; verify load-bearing "
        "claims against the notebook."
    )
    return "  " + "<br>\n  ".join(parts)


def render_page(
    *,
    page: dict,
    pages: list[dict],
    site_title: str,
    body: str,
    meta: dict,
    provenance: bool = False,
) -> str:
    return PAGE_SHELL.format(
        title=html.escape(page["title"]),
        site_title=html.escape(site_title),
        description=html.escape(page.get("purpose", ""))[:300],
        nav_links=nav_links(pages, page["slug"]),
        body=body,
        colophon=colophon(meta),
        mermaid_tag="",
        provenance_panel=PROVENANCE_PANEL if provenance else "",
        provenance_scripts=PROVENANCE_SCRIPTS if provenance else "",
    )
