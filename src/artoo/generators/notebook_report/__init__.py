"""The notebook-report generator: render a report *from* a flip notebook.

This is the read-direction sibling of the explainer. The explainer analyses a
repo and *writes into* a fresh notebook; notebook-report treats an existing flip
notebook as canonical and *renders it out* into a report artifact.

Why a generator (``artoo generate notebook-report``) and not ``artoo build
--from-notebook`` — the receipt's alternative:

- ``artoo build`` verifies and refreshes an *existing* artifact (runs its build
  commands, the firewall, the provenance projection) and stamps ``updated``. It
  is a checker, not an author. Overloading it with ``--from-notebook`` would
  conflate "verify my site" with "produce my site's content".
- The generator plug-point already carries the create-or-reuse-artifact
  contract, self-documenting ``--help``, and the deterministic-fallback idiom
  the explainer established. notebook-report is that same shape pointed the
  other way, so it belongs alongside ``explainer`` in ``artoo.generators``.

Fully deterministic: no worker CLIs, no model calls, no agent delegation. It
consumes the notebook's ``flip-render/1`` projection (via the shared provenance
machinery, honouring flip's visibility policy) plus the current draft, and
renders. Same notebook in, same page out.
"""

from __future__ import annotations

import html
import os
import re
from datetime import date
from pathlib import Path

import click

from ... import __version__
from ... import flip_read
from ... import manifest as manifest_mod
from ... import provenance as provenance_mod
from ... import scaffold
from . import markdown as md_mod
from . import templates

#: Draft filenames preferred as the single body source, in order. When none is
#: present the generator concatenates every ``*.md`` in the draft dir except the
#: changelog.
PRIMARY_DRAFT_NAMES = ("index.md", "draft.md", "report.md")
_VERSION_DIR = re.compile(r"^v(\d+)$")

STATUS_ORDER = ["verified", "needs-2nd", "asserted", "proposed"]
GRADE_ORDER = ["A", "B", "C", "?"]


def find_draft_dir(nb: Path) -> Path | None:
    """The notebook's current draft directory (SPEC §11), if any.

    Prefers the ``drafts/current`` symlink; falls back to the highest-numbered
    ``drafts/vN``. Returns ``None`` when the notebook has no drafts.
    """
    drafts = nb / "drafts"
    if not drafts.is_dir():
        return None
    current = drafts / "current"
    if current.exists() and current.is_dir():
        return current
    versions = [
        p for p in drafts.iterdir() if p.is_dir() and _VERSION_DIR.match(p.name)
    ]
    if not versions:
        return None
    return max(versions, key=lambda p: int(_VERSION_DIR.match(p.name).group(1)))


def read_draft_markdown(draft_dir: Path) -> str:
    """Assemble the draft's Markdown body.

    A single primary file (``index.md`` / ``draft.md`` / ``report.md``) wins;
    otherwise every ``*.md`` except ``changelog.md`` is concatenated in sorted
    order. Returns ``""`` when the directory holds no usable Markdown.
    """
    for name in PRIMARY_DRAFT_NAMES:
        primary = draft_dir / name
        if primary.is_file():
            return primary.read_text(encoding="utf-8")
    parts = [
        p.read_text(encoding="utf-8")
        for p in sorted(draft_dir.glob("*.md"))
        if p.is_file() and p.name.lower() != "changelog.md"
    ]
    return "\n\n".join(parts)


def _skeleton_body(data: dict) -> str:
    """An honest structured skeleton from the projection.

    Questions, claims grouped by status, sources graded — every entity cited by
    its stable flip id so the kit's claim-anchor hydrator wires it to the panel.
    Clearly marked as a skeleton, not authored prose.
    """
    parts = [
        '<div class="callout callout--warn"><span class="callout-title">'
        "Skeleton — no draft</span>The notebook has no draft "
        "(<code>drafts/current</code> or <code>drafts/vN</code>), so this page is "
        "an honest structured projection of the notebook: its open questions, its "
        "claims grouped by verification status, and its sources by grade. Write "
        "the narrative as a flip draft and regenerate to replace this.</div>"
    ]

    questions = data.get("questions") or []
    if questions:
        parts.append("<h2>Questions</h2><ul>")
        for q in questions:
            qid = html.escape(str(q.get("id", "")))
            text = html.escape(str(q.get("text", "")))
            status = html.escape(str(q.get("status", "")))
            parts.append(f"<li>[{qid}] {text} — <em>{status}</em></li>")
        parts.append("</ul>")

    claims = data.get("claims") or []
    if claims:
        parts.append("<h2>Claims by status</h2>")
        by_status: dict[str, list[dict]] = {}
        for c in claims:
            by_status.setdefault(str(c.get("status", "asserted")), []).append(c)
        ordered = [s for s in STATUS_ORDER if s in by_status]
        ordered += [s for s in sorted(by_status) if s not in STATUS_ORDER]
        for status in ordered:
            parts.append(f"<h3>{html.escape(status)}</h3><ul>")
            for c in by_status[status]:
                cid = html.escape(str(c.get("id", "")))
                text = html.escape(str(c.get("text", "")))
                lb = " <strong>(load-bearing)</strong>" if c.get("load_bearing") else ""
                parts.append(f"<li>[{cid}] {text}{lb}</li>")
            parts.append("</ul>")

    sources = data.get("sources") or []
    if sources:
        parts.append("<h2>Sources by grade</h2>")
        by_grade: dict[str, list[dict]] = {}
        for s in sources:
            by_grade.setdefault(str(s.get("grade") or "?"), []).append(s)
        ordered = [g for g in GRADE_ORDER if g in by_grade]
        ordered += [g for g in sorted(by_grade) if g not in GRADE_ORDER]
        for grade in ordered:
            parts.append(f"<h3>Grade {html.escape(grade)}</h3><ul>")
            for s in by_grade[grade]:
                sid = html.escape(str(s.get("id", "")))
                title = html.escape(str(s.get("title") or s.get("slug") or ""))
                kind = html.escape(str(s.get("kind", "")))
                indep = html.escape(str(s.get("independence", "")))
                meta = ", ".join(bit for bit in (kind, indep) if bit)
                suffix = f" <em>({meta})</em>" if meta else ""
                parts.append(f"<li>[{sid}] {title}{suffix}</li>")
            parts.append("</ul>")

    if not (questions or claims or sources):
        parts.append(
            "<p>The notebook projection carries no questions, claims, or sources "
            "yet — there is nothing to skeleton. Capture some in the notebook and "
            "regenerate.</p>"
        )
    return "\n".join(parts)


def _article_header(kicker: str, title: str, dek: str) -> str:
    parts = [
        '<header class="article-header">',
        f'<div class="article-kicker">{html.escape(kicker)}</div>',
        f'<h1 class="article-title">{html.escape(title)}</h1>',
    ]
    if dek:
        parts.append(f'<p class="article-dek">{html.escape(dek)}</p>')
    parts.append("</header>")
    return "\n".join(parts)


@click.command()
@click.option(
    "--notebook",
    "notebook_path",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="The flip notebook root to render (a directory with an index.md).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Artifact directory (default: <notebook>-report beside the notebook).",
)
@click.option("--title", default="", help="Report title (default: the notebook title).")
@click.option(
    "--include-private",
    is_flag=True,
    help="Pass --include-private to flip (render a non-public notebook in full).",
)
def generate(notebook_path: Path, out: Path | None, title: str, include_private: bool):
    """Render a report artifact from an existing flip notebook.

    The notebook is canonical; this produces a derived, disposable render. Re-run
    it to regenerate in place — the generator owns the output directory.
    """
    nb = notebook_path.resolve()
    if not (nb / "index.md").is_file():
        raise click.ClickException(
            f"{nb} is not a flip notebook (no index.md). Point --notebook at a "
            "notebook root."
        )

    out = (out or nb.parent / f"{nb.name}-report").resolve()

    # Create or reuse the artifact.
    try:
        m = manifest_mod.load(out)
        click.echo(f"updating report at {out}")
    except FileNotFoundError:
        m = scaffold.init_artifact(
            out,
            slug=f"{nb.name}-report",
            title=title or nb.name.replace("-", " "),
            kind="report",
            description=f"A report rendered from the {nb.name} flip notebook.",
        )
        click.echo(f"created report at {out}")

    # Bind the (external, canonical) notebook by relative path and record the
    # private opt-in. Relative paths may escape the artifact dir with ``..`` for
    # the read direction — the manifest permits it (see manifest.validate).
    m.notebook = os.path.relpath(nb, m.dir)
    if include_private:
        m.research_include_private = True
    if title:
        m.title = title
    m.save()

    # Project the notebook: writes site/data/provenance.{json,js}, stamps the
    # render vintage into artifact.toml, and hands back the raw projection for
    # the skeleton. A private notebook without an opt-in (or absent flip) is not
    # fatal — we can still render an existing draft, just without the panel.
    prov = provenance_mod.ingest(m)
    with_panel = prov.status == "written"
    data = prov.data
    if prov.status == "error":
        click.secho(f"! provenance projection unavailable: {prov.note}", fg="yellow")
    elif prov.status == "skipped":
        click.secho(f"! provenance projection skipped: {prov.note}", fg="yellow")
    else:
        click.echo(
            f"provenance: {prov.counts['sources']} sources, "
            f"{prov.counts['claims']} claims → site/data/provenance.json"
        )

    # Vintage for the colophon: from the projection when we have it, else read
    # the live notebook frontmatter directly (works for private notebooks too).
    vintage = prov.vintage or flip_read.read_vintage(nb) or {}
    nb_title = (data.get("notebook", {}) or {}).get("title") or nb.name

    # Draft → HTML, or an honest skeleton from the projection.
    draft_dir = find_draft_dir(nb)
    draft_md = read_draft_markdown(draft_dir) if draft_dir else ""
    if draft_md.strip():
        source = "draft"
        body = md_mod.to_html(draft_md)
        click.echo(f"draft: rendered {draft_dir.relative_to(nb)}")
    elif data:
        source = "skeleton"
        body = _skeleton_body(data)
        click.secho("no draft found — rendered a skeleton from the projection", fg="yellow")
    else:
        raise click.ClickException(
            "the notebook has no draft and its projection is unavailable "
            f"({prov.note or 'flip refused or is absent'}), so there is nothing "
            "to render. Add a draft under drafts/, pass --include-private for a "
            "non-public notebook, or install flip."
        )

    header = _article_header(
        kicker=nb_title,
        title=m.title,
        dek=m.description if source == "draft" else "Structured projection of the notebook.",
    )
    page = {"slug": "index", "title": m.title, "purpose": m.description}
    meta = {
        "date": date.today().isoformat(),
        "artoo_version": __version__,
        "notebook_uid": vintage.get("uid", ""),
        "notebook_updated": vintage.get("updated", ""),
        "source": source,
    }
    page_html = templates.render_page(
        page=page,
        pages=[page],
        site_title=m.title,
        body=header + "\n" + body,
        meta=meta,
        provenance=with_panel,
    )
    (m.site_dir / "index.html").write_text(page_html, encoding="utf-8")

    m.updated = date.today().isoformat()
    if m.status == "draft":
        m.status = "building"
    m.save()

    click.secho(f"✓ report at {m.site_dir / 'index.html'}", fg="green")
    click.echo(
        "next: review the page, then `artoo deploy " + str(m.dir) + "`. "
        "Edits belong in the notebook — regen overwrites this render."
    )
