"""The explainer generator: a detailed, multi-page HTML explainer of a repo.

Pipeline — each stage caches into ``work/`` so interrupted runs resume:

1. inventory (deterministic)  → work/inventory.json
2. analysis fan-out (workers) → work/analysis/<unit>.md
3. site plan (synthesis)      → work/plan.json
4. pages (synthesis)          → work/pages/<slug>.html
5. assembly (deterministic)   → site/<slug>.html + vendored kit/mermaid

Without worker CLIs the generator degrades to a deterministic site built
from the inventory alone — smaller, but honest about it.
"""

from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import click

from ... import __version__, libraries
from ... import manifest as manifest_mod
from ... import scaffold, workers
from ...research import ResearchLog
from . import inventory as inventory_mod
from . import prompts, templates

MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
ANALYSIS_CONCURRENCY = 3


def _ensure_mermaid(m) -> str:
    """Make a mermaid runtime available to the site; return its site-relative
    src (or "" if none could be arranged).

    Preference order: an already-vendored copy (stability), then the
    artoo-mermaid site library (offline, pinned), then a CDN download
    recorded under [[vendor]].
    """
    lib_rel = "lib/mermaid/mermaid.min.js"
    if (m.site_dir / lib_rel).is_file():
        return lib_rel
    vendor_rel = "lib/vendor/mermaid.min.js"
    if (m.site_dir / vendor_rel).is_file():
        return vendor_rel
    try:
        libraries.get("mermaid")
        libraries.add(m, "mermaid")
        click.echo("vendored mermaid from the artoo-mermaid site library")
        return lib_rel
    except KeyError:
        pass
    try:
        libraries.vendor_url(m, "mermaid", MERMAID_URL)
        click.echo("vendored mermaid.min.js from CDN")
        return vendor_rel
    except Exception as exc:
        click.secho(
            f"! no mermaid available (install artoo-mermaid or go online): {exc}; "
            "diagrams will render as source blocks",
            fg="yellow",
        )
        return ""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unit"


def _extract_json(text: str) -> dict | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _strip_fences(text: str) -> str:
    match = re.match(r"^```(?:html)?\s*\n(.*)\n```\s*$", text.strip(), re.DOTALL)
    return match.group(1) if match else text


# -- deterministic fallbacks --------------------------------------------------


def _default_plan(inv: dict) -> dict:
    name = inv["name"]
    return {
        "site_title": f"{name} explained",
        "tagline": inv["readme"].get("first_paragraph", "")[:160],
        "pages": [
            {"slug": "index", "title": "Overview",
             "purpose": f"What {name} is and the shape of the codebase.",
             "sections": ["What this is", "By the numbers", "Where to go"]},
            {"slug": "architecture", "title": "Architecture",
             "purpose": "How the areas of the codebase relate.",
             "sections": ["Areas", "Dependencies"]},
            {"slug": "reference", "title": "Area reference",
             "purpose": "Every area of the tree with size and role.",
             "sections": ["Areas"]},
        ],
    }


def _unit_graph_mermaid(inv: dict, units: list[dict]) -> str:
    """Deterministic architecture sketch: unit nodes, import edges."""
    unit_names = {u["name"].split("/")[0] for u in units}
    edges = set()
    for module in inv["python"]["modules"]:
        src_top = Path(module["path"]).parts[0] if "/" in module["path"] else "root"
        for imp in module["imports"]:
            if imp in unit_names and imp != src_top and src_top in unit_names:
                edges.add((src_top, imp))
    lines = ["graph LR"]
    for name in sorted(unit_names):
        node = _slugify(name)
        lines.append(f'  {node}["{name}"]')
    for src, dst in sorted(edges):
        lines.append(f"  {_slugify(src)} --> {_slugify(dst)}")
    return "\n".join(lines)


def _fallback_body(page: dict, inv: dict, units: list[dict], plan: dict,
                   degraded: bool) -> str:
    name = inv["name"]
    parts = [
        '<header class="article-header">',
        f'<div class="article-kicker">{html.escape(plan["site_title"])}</div>',
        f'<h1 class="article-title">{html.escape(page["title"])}</h1>',
        f'<p class="article-dek">{html.escape(page["purpose"])}</p>',
        "</header>",
    ]
    if degraded:
        parts.append(
            '<div class="callout callout--warn"><span class="callout-title">'
            "Deterministic build</span>No analysis workers were available, so "
            "this page is built from the repo inventory alone. Re-run with "
            "<code>codex</code>/<code>claude</code> on PATH for the full "
            "explainer.</div>"
        )

    if page["slug"] == "index":
        readme = inv["readme"]
        if readme.get("first_paragraph"):
            parts.append(f"<p>{html.escape(readme['first_paragraph'])}</p>")
        git = inv["git"]
        stats = [
            (f"{inv['python']['source_loc']:,}", "source LOC (py)"),
            (f"{inv['python']['test_loc']:,}", "test LOC (py)"),
            (str(len(units)), "areas"),
            (str(git.get("commits", 0)), "commits"),
        ]
        cells = "".join(
            f'<div class="stat"><span class="value">{v}</span>'
            f'<span class="label">{label}</span></div>'
            for v, label in stats
        )
        parts.append(f'<div class="stat-row">{cells}</div>')
        cards = "".join(
            f'<a class="card" href="{p["slug"]}.html"><h3>{html.escape(p["title"])}</h3>'
            f"<p>{html.escape(p['purpose'])}</p></a>"
            for p in plan["pages"]
            if p["slug"] != "index"
        )
        parts.append(f'<div class="card-grid">{cards}</div>')
    elif page["slug"] == "architecture":
        mermaid = _unit_graph_mermaid(inv, units)
        parts.append(
            f'<div class="diagram"><pre class="mermaid">{html.escape(mermaid)}</pre></div>'
        )
        parts.append(
            "<p>Edges are derived from Python import statements between "
            "top-level areas — a sketch of coupling, not a full call graph.</p>"
        )
    else:
        rows = "".join(
            f"<tr><td><code>{html.escape(u['name'])}</code></td>"
            f"<td>{u['loc']:,}</td><td>{len(u['files'])}</td></tr>"
            for u in units
        )
        parts.append(
            "<table><thead><tr><th>Area</th><th>LOC</th><th>Files</th></tr>"
            f"</thead><tbody>{rows}</tbody></table>"
        )
        packages = inv["python"]["packages"]
        if packages:
            rows = "".join(
                f"<tr><td><code>{html.escape(p['path'])}</code></td>"
                f"<td>{html.escape(p['name'])}</td>"
                f"<td>{html.escape(p['description'])}</td></tr>"
                for p in packages
            )
            parts.append(
                f"<h2>Packages</h2><table><thead><tr><th>Path</th><th>Name</th>"
                f"<th>Description</th></tr></thead><tbody>{rows}</tbody></table>"
            )
    parts.append(f"<p>Explainer for <code>{html.escape(name)}</code> — see the "
                 'colophon below for how this was generated.</p>')
    return "\n".join(parts)


# -- the command ---------------------------------------------------------------


@click.command()
@click.option("--repo", type=click.Path(exists=True, path_type=Path), default=Path("."),
              help="Repository to explain.")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Artifact directory (default: <repo>/site/explainer).")
@click.option("--title", default="", help="Site title (default: '<name> explained').")
@click.option("--fresh", is_flag=True, help="Ignore cached stages; regenerate everything.")
@click.option("--max-units", default=inventory_mod.MAX_UNITS, show_default=True,
              help="Cap on analysis units.")
def generate(repo: Path, out: Path | None, title: str, fresh: bool, max_units: int):
    """Build a detailed multi-page explainer of a code repository."""
    repo = repo.resolve()
    out = (out or repo / "site" / "explainer").resolve()
    inventory_mod.MAX_UNITS = max_units

    # Artifact: create or reuse.
    try:
        m = manifest_mod.load(out)
        click.echo(f"updating artifact at {out}")
    except FileNotFoundError:
        m = scaffold.init_artifact(
            out,
            slug=f"{repo.name}-explainer",
            title=title or f"{repo.name} explained",
            kind="explainer",
            description=f"A generated explainer of the {repo.name} repository.",
        )
        click.echo(f"created artifact at {out}")

    work = m.dir / "work"
    exclude = ()
    if out.is_relative_to(repo):
        exclude = (str(out.relative_to(repo)) + "/",)

    # 1. inventory
    inv = inventory_mod.load_or_take(repo, work, fresh=fresh, exclude=exclude)
    units = inventory_mod.analysis_units(inv)
    click.echo(f"inventory: {sum(f['loc'] for f in inv['files']):,} LOC across "
               f"{len(inv['files'])} files → {len(units)} analysis units")

    overrides = m.workers
    analysis_worker = workers.resolve("analysis", overrides)
    synthesis_worker = workers.resolve("synthesis", overrides)
    have_analysis = workers.is_available(analysis_worker)
    have_synthesis = workers.is_available(synthesis_worker)
    if not have_analysis:
        click.secho(f"! analysis worker {analysis_worker!r} unavailable — "
                    "skipping per-area analysis", fg="yellow")
    if not have_synthesis:
        click.secho(f"! synthesis worker {synthesis_worker!r} unavailable — "
                    "deterministic pages only", fg="yellow")

    with ResearchLog(m, tool="explainer") as log:
        # 2. analysis fan-out
        briefs: dict[str, str] = {}
        analysis_dir = work / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        readme_hint = inv["readme"].get("first_paragraph", "")

        def analyze(unit: dict) -> tuple[str, str | None]:
            slug = _slugify(unit["name"])
            cache = analysis_dir / f"{slug}.md"
            if cache.is_file() and not fresh:
                return unit["name"], cache.read_text(encoding="utf-8")
            result = workers.run(
                "analysis",
                prompts.analysis_prompt(inv["name"], unit, readme_hint),
                cwd=repo,
                overrides=overrides,
            )
            if result.ok:
                cache.write_text(result.text, encoding="utf-8")
                return unit["name"], result.text
            (analysis_dir / f"{slug}.err").write_text(result.error, encoding="utf-8")
            return unit["name"], None

        if have_analysis:
            with ThreadPoolExecutor(max_workers=ANALYSIS_CONCURRENCY) as pool:
                for name, text in pool.map(analyze, units):
                    if text:
                        briefs[name] = text
                        click.echo(f"  analyzed {name}")
                        log.add_source(
                            str(analysis_dir / f"{_slugify(name)}.md"),
                            note=f"analysis brief for {name}",
                        )
                    else:
                        click.secho(f"  ✗ analysis failed for {name} "
                                    f"(see work/analysis/)", fg="yellow")
        degraded = not briefs

        # 3. plan
        plan_cache = work / "plan.json"
        plan = None
        if plan_cache.is_file() and not fresh:
            plan = json.loads(plan_cache.read_text(encoding="utf-8"))
        elif briefs and have_synthesis:
            result = workers.run(
                "synthesis", prompts.plan_prompt(inv, briefs), overrides=overrides
            )
            if result.ok:
                plan = _extract_json(result.text)
        if not plan or not plan.get("pages"):
            plan = _default_plan(inv)
        if title:
            plan["site_title"] = title
        if not any(p["slug"] == "index" for p in plan["pages"]):
            plan["pages"][0]["slug"] = "index"
        plan_cache.write_text(json.dumps(plan, indent=1), encoding="utf-8")
        click.echo(f"plan: {len(plan['pages'])} pages — "
                   + ", ".join(p["slug"] for p in plan["pages"]))

        # 4. pages
        pages_dir = work / "pages"
        pages_dir.mkdir(exist_ok=True)
        bodies: dict[str, str] = {}
        for page in plan["pages"]:
            cache = pages_dir / f"{page['slug']}.html"
            if cache.is_file() and not fresh:
                bodies[page["slug"]] = cache.read_text(encoding="utf-8")
                continue
            body = ""
            if briefs and have_synthesis:
                result = workers.run(
                    "synthesis",
                    prompts.page_prompt(inv, plan, page, briefs),
                    overrides=overrides,
                )
                if result.ok:
                    body = _strip_fences(result.text)
                else:
                    click.secho(f"  ✗ synthesis failed for {page['slug']}: "
                                f"{result.error[:120]}", fg="yellow")
            if not body:
                body = _fallback_body(page, inv, units, plan, degraded)
            cache.write_text(body, encoding="utf-8")
            bodies[page["slug"]] = body
            click.echo(f"  wrote {page['slug']}")

        # 5. assembly
        uses_mermaid = any('class="mermaid"' in b for b in bodies.values())
        mermaid_src = _ensure_mermaid(m) if uses_mermaid else ""

        meta = {
            "date": date.today().isoformat(),
            "artoo_version": __version__,
            "repo_name": inv["name"],
            "commit": inv["git"].get("head", ""),
            "workers": (
                f"analysis: {analysis_worker if briefs else 'none'}, "
                f"synthesis: {synthesis_worker if (briefs and have_synthesis) else 'none'}"
            ),
        }
        for page in plan["pages"]:
            html_text = templates.render_page(
                page=page, pages=plan["pages"],
                site_title=plan["site_title"], body=bodies[page["slug"]],
                meta=meta, mermaid_src=mermaid_src,
            )
            (m.site_dir / f"{page['slug']}.html").write_text(html_text, encoding="utf-8")

        log.note(f"generated {len(plan['pages'])} pages "
                 f"({'degraded' if degraded else 'full'} mode)")

    m.updated = date.today().isoformat()
    if m.status == "draft":
        m.status = "building"
    m.save()

    click.secho(f"✓ explainer at {m.site_dir / 'index.html'}", fg="green")
    click.echo("next: review the pages, then `artoo deploy " + str(m.dir) + "`")
