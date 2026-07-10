"""The artoo CLI."""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from . import __version__, build as build_mod, deploy as deploy_mod
from . import discover, firewall, generators
from . import libraries as libraries_mod
from . import manifest as manifest_mod
from . import scaffold
from .manifest import KINDS, Manifest


def _resolve(path: str | None) -> Manifest:
    try:
        return discover.resolve_artifact(Path(path) if path else None)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc


@click.group()
@click.version_option(version=__version__, prog_name="artoo")
def main():
    """Generate and manage artifacts — self-contained HTML mini-sites
    that pair presentation with the research backing it."""


@main.command()
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--slug", default="", help="Artifact slug (default: directory name).")
@click.option("--title", default="", help="Human title.")
@click.option("--kind", default="report", type=click.Choice(KINDS), show_default=True)
@click.option("--description", default="")
@click.option("--notebook", is_flag=True, help="Also create a research notebook.")
def init(path: Path, slug: str, title: str, kind: str, description: str, notebook: bool):
    """Scaffold a new artifact at PATH."""
    try:
        m = scaffold.init_artifact(
            path, slug=slug, title=title, kind=kind,
            description=description, with_notebook=notebook,
        )
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"created {m.dir}")
    click.echo(f"  manifest  {m.path.relative_to(Path.cwd()) if m.path.is_relative_to(Path.cwd()) else m.path}")
    click.echo(f"  site      {m.site}/index.html")
    if notebook:
        click.echo("  notebook  notebook/")


@main.command(name="list")
@click.argument("root", type=click.Path(exists=True, path_type=Path), default=".")
def list_cmd(root: Path):
    """Discover artifacts under ROOT."""
    paths = discover.find_artifacts(root)
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
def status(path: Path | None):
    """Manifest health, firewall report, and library drift for an artifact."""
    m = _resolve(str(path) if path else None)
    click.echo(f"{m.slug} — {m.title}")
    click.echo(f"  kind {m.kind} · status {m.status} · deploy {m.deploy_target or '(unset)'}")

    problems = m.validate() + firewall.check(m)
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

    if not problems:
        click.secho("  ✓ manifest and firewall clean", fg="green")


@main.command(name="build")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--dry-run", is_flag=True)
def build_cmd(path: Path | None, dry_run: bool):
    """Run the artifact's build commands, then verify the site."""
    m = _resolve(str(path) if path else None)
    result = build_mod.build(m, dry_run=dry_run)
    for command in result.ran:
        click.echo(f"{'would run' if dry_run else 'ran'}: {command}")
    for problem in result.problems:
        click.secho(f"✗ {problem}", fg="red")
    if result.ok:
        click.secho(f"✓ site ready: {m.site_dir}", fg="green")
    else:
        raise SystemExit(1)


@main.command(name="deploy")
@click.argument("path", type=click.Path(path_type=Path), required=False)
@click.option("--dry-run", is_flag=True, help="Show what would happen; touch nothing remote.")
@click.option("--skip-build", is_flag=True, help="Skip build commands before deploying.")
def deploy_cmd(path: Path | None, dry_run: bool, skip_build: bool):
    """Firewall-stage the site, then hand it to the deploy adapter."""
    m = _resolve(str(path) if path else None)
    if not m.deploy_target:
        raise click.ClickException(
            "no [deploy] target in the manifest. Set one, e.g.\n"
            '  [deploy]\n  target = "github-pages"'
        )

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


# -- doctor -------------------------------------------------------------------


@main.command()
@click.argument("root", type=click.Path(exists=True, path_type=Path), default=".")
def doctor(root: Path):
    """Repo-wide coherence report over every artifact under ROOT."""
    paths = discover.find_artifacts(root)
    if not paths:
        click.echo(f"no artifacts under {root.resolve()}")
        return
    healthy = 0
    for p in paths:
        try:
            m = manifest_mod.load(p)
        except Exception as exc:
            click.secho(f"✗ {p}: unreadable manifest ({exc})", fg="red")
            continue
        problems = m.validate() + firewall.check(m)
        drifted = [r for r in libraries_mod.status(m) if r["state"] != "intact"]
        if not problems and not drifted:
            healthy += 1
            continue
        click.echo(f"{m.slug} ({p})")
        for problem in problems:
            click.secho(f"  ✗ {problem}", fg="red")
        for row in drifted:
            click.secho(f"  ! lib {row['name']}: {row['state']}", fg="yellow")
    click.echo(f"{healthy}/{len(paths)} artifacts clean")


if __name__ == "__main__":
    main()
