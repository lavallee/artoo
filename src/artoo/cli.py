"""The artoo CLI."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import click

from . import __version__, build as build_mod, content as content_mod
from . import data as data_mod, deploy as deploy_mod
from . import agent_guide, discover, docs as docs_mod, firewall, flip_read, generators
from . import libraries as libraries_mod
from . import manifest as manifest_mod
from . import provenance as provenance_mod
from . import scaffold, serve as serve_mod, skill as skill_mod, vizier as vizier_mod
from . import verify as verify_mod
from .codegraph_cli import map_group
from .manifest import FORMS, KINDS, Manifest


def _resolve(path: str | None) -> Manifest:
    try:
        return discover.resolve_artifact(Path(path) if path else None)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc


def _refresh_guide(m: Manifest) -> None:
    """Rewrite AGENTS.md after the vendored set changes.

    The guide's class tables are generated from the vendored stylesheets, so
    vendoring a library or moving to a new version is exactly the moment they
    stop being true. Regenerating here means the contract in the artifact can
    never describe a version it is not carrying.
    """
    path = agent_guide.write(m)
    click.echo(f"refreshed {path.name} for the new vendored set")


def _declared_source_problems(m: Manifest) -> list[str]:
    problems = content_mod.render(m, dry_run=True).problems
    problems.extend(data_mod.pack(m, dry_run=True).problems)
    problems.extend(provenance_mod.evidence_source_problems(m))
    return problems


def _deploy_doctor_gate(m: Manifest, allow_errors: bool) -> None:
    """Run flip doctor on the attached notebook; block on ERROR findings."""
    nb = provenance_mod.attached_notebook(m)
    if nb is None:
        return
    if not flip_read.available():
        click.echo("  (flip not installed — skipping the doctor pre-publish gate)")
        return
    findings, reason = flip_read.doctor_json(nb)
    if findings is None:
        click.echo(f"  (flip doctor unavailable — skipping gate: {reason})")
        return
    errors = [f for f in findings if str(f.get("level", "")).upper() == "ERROR"]
    warns = [f for f in findings if str(f.get("level", "")).upper() == "WARN"]
    if warns:
        click.secho(f"  ! flip doctor: {len(warns)} WARN finding(s) on the notebook", fg="yellow")
    if not errors:
        if not warns:
            click.secho("  ✓ flip doctor: no ERROR findings on the notebook", fg="green")
        return
    for f in errors:
        click.secho(f"  ✗ flip doctor [{f.get('code', '?')}]: {f.get('message', '')}", fg="red")
    if allow_errors:
        click.secho("  ! publishing despite doctor ERRORs (--allow-doctor-errors)", fg="yellow")
        return
    raise click.ClickException(
        f"flip doctor found {len(errors)} ERROR-level finding(s) on the attached "
        "notebook; fix them, or re-run with --allow-doctor-errors to publish anyway."
    )


@click.group()
@click.version_option(version=__version__, prog_name="artoo")
def main():
    """Generate and manage artifacts — self-contained HTML mini-sites
    that pair presentation with the research backing it.

    New here? `artoo docs quickstart` is the golden path, and `artoo docs`
    lists every topic including the layout vocabulary each site library
    defines. `artoo init` writes concise working rules plus an on-demand full
    reference into the artifact, so the contract travels with the work.
    """


main.add_command(map_group)


@main.command()
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--slug", default="", help="Artifact slug (default: directory name).")
@click.option("--title", default="", help="Human title.")
@click.option("--kind", default="report", type=click.Choice(KINDS), show_default=True)
@click.option(
    "--form",
    default=None,
    type=click.Choice(FORMS),
    help="Presentation form (inferred from --kind when omitted).",
)
@click.option("--description", default="")
@click.option("--notebook", is_flag=True, help="Also create a research notebook.")
def init(
    path: Path,
    slug: str,
    title: str,
    kind: str,
    form: str | None,
    description: str,
    notebook: bool,
):
    """Scaffold a new artifact at PATH."""
    try:
        m = scaffold.init_artifact(
            path, slug=slug, title=title, kind=kind, form=form or "",
            description=description, with_notebook=notebook,
        )
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"created {m.dir}")
    click.echo(f"  manifest  {m.path.relative_to(Path.cwd()) if m.path.is_relative_to(Path.cwd()) else m.path}")
    click.echo(f"  site      {m.site}/index.html")
    click.echo("  brief     work/artifact-brief.md (private)")
    click.echo(f"  contract  {agent_guide.GUIDE_NAME} — concise working rules")
    click.echo(f"  reference {agent_guide.REFERENCE_NAME} — full vocabulary, on demand")
    if notebook:
        click.echo("  notebook  notebook/")
    click.echo(f"\nRead {m.dir / agent_guide.GUIDE_NAME} before authoring; "
               f"`artoo docs` has the rest.")


@main.command(name="vizier-guide")
@click.argument("job")
@click.option("--context", default=None, help="Headline, caption, source, or implementation notes.")
@click.option("--family", default=None, help="Optional FT Visual Vocabulary family.")
@click.option(
    "--series-count", type=click.IntRange(min=1), default=None, help="Series/category count."
)
@click.option("--form-count", type=click.IntRange(min=1), default=None, help="Forms to return.")
@click.option(
    "--prior-count", type=click.IntRange(min=1), default=None, help="Prior-art signals to return."
)
@click.option(
    "--semantic/--no-semantic",
    default=None,
    help="Explicitly enable or disable Vizier's local semantic retrieval.",
)
@click.option("--artifact", type=click.Path(path_type=Path), default=None)
def vizier_guide(
    job: str,
    context: str | None,
    family: str | None,
    series_count: int | None,
    form_count: int | None,
    prior_count: int | None,
    semantic: bool | None,
    artifact: Path | None,
):
    """Record optional local Vizier implementation guidance for an artifact."""
    click.secho(
        "deprecated: Vizier is an optional recipe, not part of Artoo's authoring contract",
        fg="yellow",
        err=True,
    )
    m = _resolve(str(artifact) if artifact else None)
    try:
        receipt = vizier_mod.run_guide(
            m,
            job,
            context=context,
            family=family,
            series_count=series_count,
            form_count=form_count,
            prior_count=prior_count,
            semantic=semantic,
        )
    except vizier_mod.VizierGuideError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"wrote private Vizier guidance receipt: {receipt.relative_to(m.dir)}")


@main.command(name="list")
@click.argument("root", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def list_cmd(root: Path, as_json: bool):
    """Discover artifacts under ROOT."""
    paths = discover.find_artifacts(root)

    if as_json:
        # Indexers and servers need the inventory without re-implementing
        # manifest parsing (and without guessing that site defaults to "site",
        # which several real artifacts override). Invalid manifests are
        # reported rather than dropped, so a typo never silently shrinks a
        # caller's inventory.
        entries = []
        for p in paths:
            try:
                m = manifest_mod.load(p)
            except Exception as exc:
                entries.append({"path": str(p), "error": str(exc)})
                continue
            entries.append(
                {
                    "path": str(p),
                    "slug": m.slug,
                    "title": m.title,
                    "description": m.description,
                    "kind": m.kind,
                    "form": m.effective_form,
                    "status": m.status,
                    "created": m.created,
                    "updated": m.updated,
                    "site": m.site,
                    "site_dir": str(m.site_dir),
                    "deploy_target": m.deploy_target,
                }
            )
        click.echo(json.dumps(entries, indent=2))
        return

    if not paths:
        click.echo(f"no artifacts under {root.resolve()}")
        return
    for p in paths:
        try:
            m = manifest_mod.load(p)
            label = f"{m.slug:24} {m.kind:16} {m.status:9}"
            target = m.deploy_target or "-"
            click.echo(f"{label} {target:14} {p}")
        except Exception as exc:
            click.echo(f"{'?':24} {'invalid':16} {'':9} {'':14} {p}  ({exc})")


@main.command()
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def status(path: Path | None, as_json: bool):
    """Manifest health, firewall report, and library drift for an artifact."""
    m = _resolve(str(path) if path else None)
    findings = libraries_mod.markup_check(m)
    verification = verify_mod.static(m) if m.site_dir.is_dir() else verify_mod.VerificationResult()

    if as_json:
        problems = (
            m.validate()
            + _declared_source_problems(m)
            + firewall.check(m)
            + verification.problems
        )
        if m.site_dir.is_dir():
            problems += provenance_mod.data_json_problems(m.site_dir)
        report = {
            "path": str(m.dir),
            "slug": m.slug,
            "title": m.title,
            "kind": m.kind,
            "form": m.effective_form,
            "status": m.status,
            "deploy_target": m.deploy_target,
            "site_dir": str(m.site_dir),
            "problems": problems,
            "warnings": verification.warnings,
            "withheld": [str(r) for r in firewall.withheld(m.site_dir)]
            if m.site_dir.is_dir()
            else [],
            "libraries": libraries_mod.status(m),
            # Kept separate from `problems`: a caller fixing markup wants the
            # class and the suggestion as fields, not a sentence to re-parse.
            "markup": [
                {
                    "file": f.file,
                    "class": f.cls,
                    "library": f.library,
                    "namespace": f.namespace,
                    "suggestion": f.suggestion,
                    "message": f.message(),
                }
                for f in findings
            ],
            "render": provenance_mod.staleness(m),
            "ok": not problems and not findings,
        }
        click.echo(json.dumps(report, indent=2))
        return

    click.echo(f"{m.slug} — {m.title}")
    click.echo(
        f"  kind {m.kind} · form {m.effective_form} · status {m.status} · "
        f"deploy {m.deploy_target or '(unset)'}"
    )

    problems = (
        m.validate()
        + _declared_source_problems(m)
        + firewall.check(m)
        + verification.problems
    )
    if m.site_dir.is_dir():
        problems += provenance_mod.data_json_problems(m.site_dir)
    for problem in problems:
        click.secho(f"  ✗ {problem}", fg="red")

    if m.site_dir.is_dir():
        held = firewall.withheld(m.site_dir)
        if held:
            click.echo(f"  firewall withholds {len(held)} file(s) inside site/:")
            for rel in held[:8]:
                click.echo(f"    - {rel}")

    for row in libraries_mod.status(m):
        mark = "✓" if row["state"] == "intact" else "!"
        click.echo(f"  {mark} lib {row['name']} {row['version']} — {row['state']}")

    # Render freshness against the attached notebook — advisory, never a failure.
    fresh = provenance_mod.staleness(m)
    if fresh["state"] == "fresh":
        click.secho(f"  ✓ render fresh — {fresh['detail']}", fg="green")
    elif fresh["state"] == "stale":
        click.secho(f"  ! render stale — {fresh['detail']}", fg="yellow")
    elif fresh["state"] == "never":
        click.secho(f"  ! render vintage — {fresh['detail']}", fg="yellow")
    elif fresh["state"] == "unknown":
        click.secho(f"  ? notebook vintage — {fresh['detail']}", fg="yellow")

    for finding in findings:
        click.secho(f"  ✗ {finding.message()}", fg="red")

    for warning in verification.warnings:
        click.secho(f"  ! {warning}", fg="yellow")

    if not problems and not findings:
        click.secho("  ✓ manifest, firewall, markup, and static verification clean", fg="green")


@main.command(name="build")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--dry-run", is_flag=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def build_cmd(path: Path | None, dry_run: bool, as_json: bool):
    """Run the artifact's build commands, then verify the site."""
    m = _resolve(str(path) if path else None)
    result = build_mod.build(m, dry_run=dry_run)

    if as_json:
        click.echo(
            json.dumps(
                {
                    "ok": result.ok,
                    "path": str(m.dir),
                    "slug": m.slug,
                    "site_dir": str(m.site_dir),
                    "dry_run": dry_run,
                    "ran": result.ran,
                    "generated": result.generated,
                    "problems": result.problems,
                    "warnings": result.warnings,
                    "withheld": result.withheld,
                    "stamped": result.stamped,
                    "provenance": result.provenance,
                },
                indent=2,
            )
        )
        raise SystemExit(0 if result.ok else 1)

    for command in result.ran:
        click.echo(f"{'would run' if dry_run else 'ran'}: {command}")
    if result.generated:
        click.echo(f"generated {len(result.generated)} file(s)")
    if result.provenance:
        click.echo(result.provenance)
    for problem in result.problems:
        click.secho(f"✗ {problem}", fg="red")
    for warning in result.warnings:
        click.secho(f"! {warning}", fg="yellow")
    if result.ok:
        if result.stamped:
            click.echo(f"stamped updated = {result.stamped}")
        click.secho(f"✓ site ready: {m.site_dir}", fg="green")
    else:
        raise SystemExit(1)


@main.command(name="verify")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--browser", "use_browser", is_flag=True, help="Also run optional Chromium checks.")
@click.option(
    "--screenshots",
    type=click.Path(path_type=Path),
    default=None,
    help="Write phone and desktop screenshots (requires --browser).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def verify_cmd(
    path: Path | None,
    use_browser: bool,
    screenshots: Path | None,
    as_json: bool,
):
    """Check links, assets, markup, offline behavior, and optionally Chromium."""
    m = _resolve(str(path) if path else None)
    if screenshots is not None and not use_browser:
        raise click.ClickException("--screenshots requires --browser")
    screenshot_dir = None
    if screenshots is not None:
        screenshot_dir = screenshots if screenshots.is_absolute() else m.dir / screenshots
    result = verify_mod.run(m, use_browser=use_browser, screenshots=screenshot_dir)
    if as_json:
        click.echo(
            json.dumps(
                {
                    "ok": result.ok,
                    "problems": result.problems,
                    "warnings": result.warnings,
                    "screenshots": [str(path) for path in result.screenshots],
                },
                indent=2,
            )
        )
        raise SystemExit(0 if result.ok else 1)
    for problem in result.problems:
        click.secho(f"✗ {problem}", fg="red")
    for warning in result.warnings:
        click.secho(f"! {warning}", fg="yellow")
    for image in result.screenshots:
        click.echo(f"screenshot {image}")
    if result.ok:
        click.secho("✓ static verification clean" + ("; browser clean" if use_browser else ""), fg="green")
    else:
        raise SystemExit(1)


@main.command(name="provenance")
@click.argument("path", type=click.Path(path_type=Path), required=False)
def provenance_cmd(path: Path | None):
    """Project declared evidence or a flip notebook into site/data/provenance.json."""
    m = _resolve(str(path) if path else None)
    result = provenance_mod.ingest(m)
    if result.status == "written":
        c = result.counts
        grades = " / ".join(f"{n} {g}" for g, n in sorted(c["grades"].items())) or "none graded"
        click.echo(f"wrote {result.path.relative_to(m.dir)}")
        if m.evidence_source:
            click.echo(f"  evidence  {m.evidence_source} · artoo-evidence/1")
        else:
            click.echo(
                f"  notebook  {result.vintage.get('uid') or '?'} · "
                f"updated {result.vintage.get('updated') or '?'}"
            )
        click.echo(f"  sources   {c['sources']} ({grades})")
        click.echo(f"  claims    {c['claims']} · {c['load_bearing']} load-bearing")
        note = (
            "  ✓ neutral evidence projected"
            if m.evidence_source
            else "  ✓ render vintage recorded in artifact.toml"
        )
        click.secho(note, fg="green")
    elif result.status == "skipped":
        click.echo(f"skipped: {result.note}")
    else:
        raise click.ClickException(result.note)


@main.command(name="serve")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--port", default=8765, show_default=True, help="Port to bind on loopback.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Interface to bind.")
@click.option("--open", "open_browser", is_flag=True, help="Open the artifact in a browser.")
@click.option("--quiet", is_flag=True, help="Suppress the per-request log.")
def serve_cmd(path: Path | None, port: int, host: str, open_browser: bool, quiet: bool):
    """Serve the artifact locally, with a JSON store behind it.

    Most artifacts read fine from `file://`. An explorer does not: a page whose
    value is the configuration a reader arrived at needs somewhere durable to
    put it. This serves exactly what a deploy would ship — the firewall-staged
    site, so a private working file is absent rather than merely unlinked — and
    adds one small API under `/_artoo/state` that reads and writes named JSON
    documents into the artifact's own `state/` directory.

    Those are real files, next to the work and committed with it. `state/` is a
    sibling of `site/`, so nothing saved here can reach a publish. The page
    talks to it through `ArtooStore` from artoo-kit, which falls back to browser
    storage — and says so — when nothing is serving.

    Loopback only, no authentication. This is a working surface, not a host.
    """
    m = _resolve(str(path) if path else None)
    try:
        httpd, publishable, state_dir = serve_mod.serve(m, host=host, port=port, quiet=quiet)
    except OSError as exc:
        raise click.ClickException(f"could not bind {host}:{port} — {exc}") from exc

    url = f"http://{host}:{port}/"
    click.echo(f"serving {m.slug} at {url}")
    click.echo(f"  site      {len(publishable)} publishable file(s) in {m.site}/, read live (firewall applied per request)")
    collections = sorted(p.name for p in state_dir.glob("*") if p.is_dir()) if state_dir.is_dir() else []
    held = f"{', '.join(collections)}" if collections else "empty"
    click.echo(f"  state     {state_dir.relative_to(m.dir)}/ — {held}")
    click.echo("  stop      ctrl-c")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nstopped")
    finally:
        httpd.server_close()


@main.command(name="deploy")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--dry-run", is_flag=True, help="Show what would happen; touch nothing remote.")
@click.option("--skip-build", is_flag=True, help="Skip build commands before deploying.")
@click.option(
    "--allow-doctor-errors",
    is_flag=True,
    help="Publish even if flip doctor reports ERROR-level findings on the notebook.",
)
def deploy_cmd(path: Path | None, dry_run: bool, skip_build: bool, allow_doctor_errors: bool):
    """Firewall-stage the site, then hand it to the deploy adapter."""
    m = _resolve(str(path) if path else None)
    if not m.deploy_target:
        raise click.ClickException(
            "no [deploy] target in the manifest. Set one, e.g.\n"
            '  [deploy]\n  target = "github-pages"'
        )

    # Pre-publish evidentiary gate: if a flip notebook is attached and flip is
    # installed, refuse on ERROR-level doctor findings about the claims and
    # citations that are about to go public. Absent flip or notebook: skip.
    _deploy_doctor_gate(m, allow_doctor_errors)

    if not skip_build:
        result = build_mod.build(m, dry_run=dry_run)
        if not result.ok:
            for problem in result.problems:
                click.secho(f"✗ {problem}", fg="red")
            raise SystemExit(1)

    try:
        adapter_cls = deploy_mod.get(m.deploy_target)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    with tempfile.TemporaryDirectory(prefix="artoo-deploy-") as tmp:
        staged = Path(tmp) / "site"
        staged_files = firewall.stage(m, staged)
        click.echo(f"staged {len(staged_files)} file(s) through the firewall")
        ctx = deploy_mod.DeployContext(
            manifest=m, staged=staged, config=m.deploy_config, dry_run=dry_run
        )
        outcome = adapter_cls().deploy(ctx)

    for action in outcome.actions:
        if action:
            click.echo(f"  {action}")
    if outcome.ok:
        click.secho(f"✓ {outcome.message}", fg="green")
    else:
        click.secho(f"✗ {outcome.message}", fg="red")
        raise SystemExit(1)


# -- lib subcommands ---------------------------------------------------------


@main.group()
def lib():
    """Manage vendored site libraries."""


@lib.command(name="list")
def lib_list():
    """Libraries available to vendor."""
    for name, library in sorted(libraries_mod.available().items()):
        click.echo(f"{name:20} {library.version:10} {library.root}")


@lib.command(name="add")
@click.argument("name")
@click.option("--artifact", type=click.Path(path_type=Path), default=None)
def lib_add(name: str, artifact: Path | None):
    """Vendor a library into the artifact's site."""
    m = _resolve(str(artifact) if artifact else None)
    try:
        record = libraries_mod.add(m, name)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"vendored {record['name']} {record['version']} → {m.site}/lib/{name}/")
    _refresh_guide(m)


@lib.command(name="status")
@click.option("--artifact", type=click.Path(path_type=Path), default=None)
def lib_status(artifact: Path | None):
    """Intact / modified / outdated state of each vendored library."""
    m = _resolve(str(artifact) if artifact else None)
    rows = libraries_mod.status(m)
    if not rows:
        click.echo("no libraries recorded in the manifest")
        return
    for row in rows:
        click.echo(f"{row['name']:20} {row['version']:10} {row['state']}")


@lib.command(name="update")
@click.argument("name")
@click.option("--artifact", type=click.Path(path_type=Path), default=None)
def lib_update(name: str, artifact: Path | None):
    """Re-vendor a library at its current version."""
    m = _resolve(str(artifact) if artifact else None)
    try:
        record = libraries_mod.update(m, name)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"updated {record['name']} → {record['version']}")
    _refresh_guide(m)


@lib.command(name="vendor")
@click.argument("name")
@click.argument("url")
@click.option("--artifact", type=click.Path(path_type=Path), default=None)
def lib_vendor(name: str, url: str, artifact: Path | None):
    """Vendor a single asset from a URL with a pinned hash."""
    m = _resolve(str(artifact) if artifact else None)
    record = libraries_mod.vendor_url(m, name, url)
    click.echo(f"vendored {name} → {record['path']} ({record['sha256'][:12]}…)")


# -- generate ---------------------------------------------------------------


class _GenerateGroup(click.Group):
    def list_commands(self, ctx):
        return sorted(generators.available())

    def get_command(self, ctx, name):
        return generators.available().get(name)


@main.command(cls=_GenerateGroup, name="generate")
def generate_cmd():
    """Run a generator plugin."""


# -- feedback -----------------------------------------------------------------


@main.command()
@click.argument("artifact", type=click.Path(path_type=Path))
@click.argument("text")
@click.option("--claim", default=None, help="Cite a claim id (e.g. C7) this feedback is about.")
@click.option("--source", default=None, help="Cite a source id (e.g. A3) this feedback is about.")
@click.option("--as-log", is_flag=True, help="Record a flip log event instead of opening a question.")
def feedback(artifact: Path, text: str, claim: str | None, source: str | None, as_log: bool):
    """Route artifact-side feedback INTO the attached flip notebook.

    The published render is never edited (SPEC §6.8): a correction re-enters the
    canonical notebook as a flip question (default) or a flip log event
    (--as-log), keyed by the cited stable id. A breadcrumb is recorded in the
    artifact's private work/feedback.jsonl. site/ is never touched.
    """
    m = _resolve(str(artifact))

    if claim and source:
        raise click.ClickException("give at most one of --claim / --source, not both.")

    nb = provenance_mod.attached_notebook(m)
    if nb is None:
        raise click.ClickException(
            "no flip notebook is attached to this artifact, so there is nowhere "
            "to route feedback. Bind one with [research] notebook = \"…\" in "
            "artifact.toml (it may point outside the artifact), then retry."
        )
    if not flip_read.available():
        raise click.ClickException(
            "flip is not installed (or ARTOO_FLIP_BIN does not resolve), so "
            "feedback cannot be routed into the notebook. Install flip, or pin it "
            "with ARTOO_FLIP_BIN, then retry."
        )

    cited = claim or source
    if cited:
        resolved, reason = flip_read.resolve_json(nb, cited)
        if resolved is None:
            raise click.ClickException(
                f"{cited} does not resolve in the attached notebook "
                f"({m.notebook}): {reason}. Check the id against the provenance panel."
            )

    # The routed text carries the artifact ref and the cited id so a reader of
    # the notebook question/log knows exactly what it is about.
    prefix = f"artifact feedback ({m.slug})"
    routed_text = f"{prefix} on [{cited}]: {text}" if cited else f"{prefix}: {text}"

    if as_log:
        ok, reason = flip_read.log_event(nb, routed_text)
        if not ok:
            raise click.ClickException(f"flip log failed: {reason}")
        routed_as = "log"
        landed = "logged an event"
    else:
        qid, reason = flip_read.question_add(nb, routed_text)
        if qid is None:
            raise click.ClickException(f"flip question add failed: {reason}")
        routed_as = f"question:{qid}" if qid else "question"
        landed = f"opened question {qid}" if qid else "opened a question"

    # Artifact-side receipt of the back-flow: private, firewalled (work/ never
    # ships). Append-only, one JSON object per line.
    breadcrumb = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ref": cited or "",
        "text": text,
        "routed_as": routed_as,
        "notebook": str(m.notebook),
    }
    work = m.dir / "work"
    work.mkdir(exist_ok=True)
    with (work / "feedback.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(breadcrumb, ensure_ascii=False) + "\n")

    click.secho(f"✓ {landed} in the notebook{f' about {cited}' if cited else ''}", fg="green")
    click.echo("  recorded in work/feedback.jsonl (private — never deployed)")


# -- doctor -------------------------------------------------------------------


@main.command()
@click.argument("root", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def doctor(root: Path, as_json: bool):
    """Repo-wide coherence report over every artifact under ROOT."""
    paths = discover.find_artifacts(root)
    reports = []
    for p in paths:
        try:
            m = manifest_mod.load(p)
        except Exception as exc:
            reports.append({"path": str(p), "error": str(exc), "ok": False})
            continue
        verification = (
            verify_mod.static(m) if m.site_dir.is_dir() else verify_mod.VerificationResult()
        )
        problems = (
            m.validate()
            + _declared_source_problems(m)
            + firewall.check(m)
            + verification.problems
        )
        if m.site_dir.is_dir():
            problems += provenance_mod.data_json_problems(m.site_dir)
        drifted = [r for r in libraries_mod.status(m) if r["state"] != "intact"]
        markup_notes = [f.message() for f in libraries_mod.markup_check(m)]
        reports.append(
            {
                "path": str(p),
                "slug": m.slug,
                "problems": problems,
                "drifted": drifted,
                "markup": markup_notes,
                "warnings": verification.warnings,
                "ok": not problems and not drifted and not markup_notes,
            }
        )

    if as_json:
        click.echo(
            json.dumps(
                {
                    "root": str(root.resolve()),
                    "artifacts": reports,
                    "clean": sum(1 for r in reports if r["ok"]),
                    "total": len(reports),
                },
                indent=2,
            )
        )
        return

    if not paths:
        click.echo(f"no artifacts under {root.resolve()}")
        return
    for report in reports:
        if report.get("error"):
            click.secho(f"✗ {report['path']}: unreadable manifest ({report['error']})", fg="red")
            continue
        if report["ok"] and not report["warnings"]:
            continue
        click.echo(f"{report['slug']} ({report['path']})")
        for problem in report["problems"]:
            click.secho(f"  ✗ {problem}", fg="red")
        for note in report["markup"]:
            click.secho(f"  ✗ {note}", fg="red")
        for warning in report["warnings"]:
            click.secho(f"  ! {warning}", fg="yellow")
        for row in report["drifted"]:
            click.secho(f"  ! lib {row['name']}: {row['state']}", fg="yellow")
    clean = sum(1 for r in reports if r["ok"])
    click.echo(f"{clean}/{len(reports)} artifacts clean")


# -- docs -------------------------------------------------------------------


@main.command(name="docs")
@click.argument("topic", required=False)
@click.option("--all", "everything", is_flag=True, help="Print every topic in one read.")
def docs_cmd(topic: str | None, everything: bool):
    """Print artoo's reference: the golden path, the manifest, the firewall,
    and the class vocabulary each site library defines.

    With no TOPIC, lists what is readable. This is the answer to "what classes
    can I use here" — the alternative is reading the vendored stylesheets.
    """
    if everything:
        click.echo(docs_mod.render_all(), nl=False)
        return
    if topic is None:
        click.echo(docs_mod.index(), nl=False)
        return
    try:
        click.echo(docs_mod.render(topic), nl=False)
    except KeyError as exc:
        raise click.ClickException(str(exc).strip("'")) from exc


# -- skill ------------------------------------------------------------------


@main.group()
def skill():
    """Install artoo's contract as an agent skill."""


@skill.command(name="install")
@click.option(
    "--dir", "target", type=click.Path(path_type=Path), default=None,
    help="Where to write the skill (default: ./.claude/skills/artoo).",
)
@click.option(
    "--user", is_flag=True, help="Install for this user (~/.claude/skills/artoo) instead."
)
def skill_install(target: Path | None, user: bool):
    """Write SKILL.md and an offline reference set for a coding agent.

    AGENTS.md teaches an agent already standing in an artifact. This teaches
    one that has merely been asked for a report, and would otherwise hand-roll
    the HTML because nothing told it artoo exists.
    """
    root = target if target is not None else skill_mod.default_dir(user=user)
    result = skill_mod.install(Path(root))
    click.echo(f"installed the artoo skill → {result.root}")
    click.echo(f"  SKILL.md + {len(result.files) - 1} reference topic(s)")


@skill.command(name="show")
def skill_show():
    """Print SKILL.md to stdout, for agent frameworks that read it from a pipe."""
    click.echo(skill_mod.skill_markdown(), nl=False)


if __name__ == "__main__":
    main()
