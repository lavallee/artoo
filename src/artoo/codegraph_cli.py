"""CLI surface for code-graph construction and interrogation."""

from __future__ import annotations

import json
from pathlib import Path

import click

from . import codegraph


def _layers(values: tuple[str, ...]) -> set[str] | None:
    return set(values) if values else None


def _write_or_echo(text: str, out: Path | None) -> None:
    if out is None:
        click.echo(text, nl=not text.endswith("\n"))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    click.echo(f"wrote {out}")


@click.group(name="map")
def map_group():
    """Build and interrogate evidence-bearing code maps."""


@map_group.command(name="build")
@click.argument("repo", type=click.Path(exists=True, file_okay=False, path_type=Path), default=".")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Graph path (default: REPO/.artoo/codegraph.json).",
)
@click.option(
    "--exclude",
    multiple=True,
    help="Repository-relative path prefix to exclude; may be repeated.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable build receipt.")
def build_cmd(repo: Path, out: Path | None, exclude: tuple[str, ...], as_json: bool):
    """Analyze REPO into an artoo-codegraph/1 JSON file."""
    repo = repo.resolve()
    target = out or repo / ".artoo" / "codegraph.json"
    if not target.is_absolute():
        target = Path.cwd() / target
    try:
        graph = codegraph.build(repo, exclude=exclude)
        codegraph.write(graph, target)
    except codegraph.CodeGraphError as error:
        raise click.ClickException(str(error)) from error
    coverage = graph["snapshot"]["coverage"]
    receipt = {
        "ok": True,
        "contract": graph["contract"],
        "path": str(target),
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "parsed_files": coverage["parsed_files"],
        "candidate_files": coverage["candidate_files"],
        "parse_failures": coverage["parse_failures"],
        "dirty": graph["snapshot"]["dirty"],
        "revision": graph["snapshot"]["revision"],
    }
    if as_json:
        click.echo(json.dumps(receipt, indent=2))
        return
    click.echo(
        f"wrote {target} — {receipt['nodes']} nodes, {receipt['edges']} edges "
        f"from {coverage['parsed_files']}/{coverage['candidate_files']} Python files"
    )
    if coverage["parse_failures"]:
        click.secho(
            f"! {len(coverage['parse_failures'])} file(s) could not be parsed; "
            "the receipt keeps their paths under snapshot.coverage.parse_failures",
            fg="yellow",
        )
    click.echo(f"next: `artoo map view {target} --format mermaid`")


@map_group.command(name="view")
@click.argument("graph_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--view", "view_name", default="overview", show_default=True)
@click.option("--focus", default="", help="Stable id, path, qualified name, or unique label.")
@click.option(
    "--direction",
    type=click.Choice(sorted(codegraph.DIRECTIONS)),
    default=None,
    help="Override the saved view direction.",
)
@click.option("--depth", type=click.IntRange(min=0), default=None)
@click.option("--budget", type=click.IntRange(min=1), default=None)
@click.option(
    "--layer",
    "layers",
    type=click.Choice(sorted(codegraph.TRUTH_CLASSES)),
    multiple=True,
    help="Truth layer to include; repeat for more than one.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(("json", "mermaid")),
    default="json",
    show_default=True,
)
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
def view_cmd(
    graph_path: Path,
    view_name: str,
    focus: str,
    direction: str | None,
    depth: int | None,
    budget: int | None,
    layers: tuple[str, ...],
    output_format: str,
    out: Path | None,
):
    """Project a bounded saved or focused view from GRAPH_PATH."""
    try:
        graph = codegraph.load(graph_path)
        view = codegraph.select_view(
            graph,
            name=view_name,
            focus=focus,
            direction=direction,
            depth=depth,
            budget=budget,
            layers=_layers(layers),
        )
    except codegraph.CodeGraphError as error:
        raise click.ClickException(str(error)) from error
    text = (
        codegraph.to_mermaid(view)
        if output_format == "mermaid"
        else json.dumps(view, indent=2, ensure_ascii=False) + "\n"
    )
    _write_or_echo(text, out)


@map_group.command(name="why")
@click.argument("graph_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("reference")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def why_cmd(graph_path: Path, reference: str, as_json: bool):
    """Explain why a node and each adjacent relationship exist."""
    try:
        graph = codegraph.load(graph_path)
        receipt = codegraph.explain(graph, reference)
    except codegraph.CodeGraphError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(json.dumps(receipt, indent=2, ensure_ascii=False))
        return
    node = receipt["node"]
    coordinate = f"{node.get('path', '(no source path)')}:{node.get('line', 1)}"
    click.echo(f"{node['label']} — {node['kind']} · {node['truth']} · {node['id']}")
    click.echo(f"  source {coordinate}")
    labels = {row["id"]: row["label"] for row in graph["nodes"]}
    for heading, edges, endpoint in (
        ("incoming", receipt["incoming"], "source"),
        ("outgoing", receipt["outgoing"], "target"),
    ):
        click.echo(f"  {heading} {len(edges)}")
        for edge in edges:
            evidence = edge["evidence"][0]
            click.echo(
                f"    {edge['kind']} · {edge['truth']} · {labels[edge[endpoint]]} — "
                f"{evidence['path']}:{evidence['line']} · {edge['reason']}"
            )


@map_group.command(name="path")
@click.argument("graph_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("source")
@click.argument("target")
@click.option(
    "--layer",
    "layers",
    type=click.Choice(sorted(codegraph.TRUTH_CLASSES)),
    multiple=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def path_cmd(
    graph_path: Path, source: str, target: str, layers: tuple[str, ...], as_json: bool
):
    """Find a shortest directed evidence path between two nodes."""
    try:
        graph = codegraph.load(graph_path)
        path = codegraph.find_path(graph, source, target, layers=_layers(layers))
    except codegraph.CodeGraphError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(json.dumps(path, indent=2, ensure_ascii=False))
        return
    for index, node in enumerate(path["nodes"]):
        click.echo(f"{index + 1}. {node['label']} [{node['kind']} · {node['truth']}]")
        if index < len(path["edges"]):
            edge = path["edges"][index]
            evidence = edge["evidence"][0]
            click.echo(
                f"   └─ {edge['kind']} [{edge['truth']}] "
                f"{evidence['path']}:{evidence['line']}"
            )


@map_group.command(name="context")
@click.argument("graph_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("question")
@click.option(
    "--budget-tokens",
    type=click.IntRange(min=32),
    default=1200,
    show_default=True,
    help="Approximate output budget; one token is estimated as four characters.",
)
@click.option("--json", "as_json", is_flag=True, help="Include scores and ranking reasons.")
def context_cmd(graph_path: Path, question: str, budget_tokens: int, as_json: bool):
    """Select question-relevant source coordinates under a token budget."""
    try:
        graph = codegraph.load(graph_path)
        ranked = codegraph.context(graph, question, budget_tokens=budget_tokens)
    except codegraph.CodeGraphError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(json.dumps(ranked, indent=2, ensure_ascii=False))
        return
    click.echo(ranked["text"], nl=not ranked["text"].endswith("\n"))


@map_group.command(name="schema")
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
def schema_cmd(out: Path | None):
    """Print the artoo-codegraph/1 JSON Schema for analyzer authors."""
    text = codegraph.schema_path().read_text(encoding="utf-8")
    _write_or_echo(text, out)
