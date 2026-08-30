import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from artoo import codegraph
from artoo.cli import main


def _graph(fake_repo: Path) -> dict:
    (fake_repo / "src" / "fakepkg" / "cli.py").write_text(
        '"""CLI for fakepkg."""\nimport fakepkg\n\n\ndef helper():\n'
        '    return fakepkg.__version__\n\n\ndef main():\n    return helper()\n',
        encoding="utf-8",
    )
    return codegraph.build(fake_repo)


def test_build_emits_valid_evidence_bearing_graph(fake_repo):
    graph = _graph(fake_repo)

    assert graph["contract"] == codegraph.CONTRACT
    assert codegraph.validate(graph) == []
    assert graph["snapshot"]["repository"] == "fake-repo"
    assert "repo" not in graph["snapshot"]  # no local absolute root leaks into the document
    assert graph["snapshot"]["coverage"]["parsed_files"] == 3

    nodes = {node["id"]: node for node in graph["nodes"]}
    assert "entrypoint:fake" in nodes
    assert "external:click" in nodes
    assert "symbol:src/fakepkg/cli.py:main" in nodes
    assert all(not Path(node["path"]).is_absolute() for node in graph["nodes"] if node.get("path"))

    edges = graph["edges"]
    assert any(edge["kind"] == "invokes" and edge["truth"] == "declared" for edge in edges)
    assert any(edge["kind"] == "imports" and edge["truth"] == "static" for edge in edges)
    call = next(edge for edge in edges if edge["kind"] == "calls")
    assert call["confidence"] == "medium"
    assert call["evidence"] == [
        {"path": "src/fakepkg/cli.py", "line": 10, "kind": "python-ast"}
    ]


def test_parse_failures_and_unsupported_languages_are_receipts(fake_repo):
    (fake_repo / "broken.py").write_text("def nope(:\n", encoding="utf-8")
    (fake_repo / "client.ts").write_text("export const x = 1;\n", encoding="utf-8")

    graph = codegraph.build(fake_repo)
    coverage = graph["snapshot"]["coverage"]

    assert coverage["candidate_files"] == 4
    assert coverage["parsed_files"] == 3
    assert coverage["parse_failures"][0]["path"] == "broken.py"
    assert coverage["unsupported_languages"] == [{"language": "typescript", "files": 1}]


def test_bounded_views_explanations_paths_and_mermaid(fake_repo):
    graph = _graph(fake_repo)
    main_id = "symbol:src/fakepkg/cli.py:main"
    helper_id = "symbol:src/fakepkg/cli.py:helper"

    view = codegraph.select_view(
        graph, focus=main_id, direction="outgoing", depth=1, budget=2
    )
    assert {node["id"] for node in view["nodes"]} == {main_id, helper_id}
    assert view["view"]["budget"] == 2
    assert view["view"]["truncated"] is True

    why = codegraph.explain(graph, main_id)
    assert why["node"]["label"] == "main"
    assert any(edge["kind"] == "invokes" for edge in why["incoming"])
    assert any(edge["kind"] == "calls" for edge in why["outgoing"])

    path = codegraph.find_path(graph, "entrypoint:fake", helper_id)
    assert [node["id"] for node in path["nodes"]] == ["entrypoint:fake", main_id, helper_id]
    assert [edge["kind"] for edge in path["edges"]] == ["invokes", "calls"]

    source = codegraph.to_mermaid(view)
    assert source.startswith("flowchart LR\n")
    assert "|calls|" in source
    assert "truth-static" in source

    calls_view = codegraph.select_view(graph, name="calls", budget=3)
    assert {edge["kind"] for edge in calls_view["edges"]} == {"invokes", "calls"}
    assert {node["id"] for node in calls_view["nodes"]} == {
        "entrypoint:fake",
        main_id,
        helper_id,
    }

    ranked = codegraph.context(graph, "Where is helper called?", budget_tokens=64)
    assert ranked["contract"] == "artoo-codegraph-context/1"
    assert ranked["estimated_tokens"] <= 64
    assert ranked["items"][0]["id"] == helper_id
    assert "query match: helper" in ranked["items"][0]["reasons"]
    assert "src/fakepkg/cli.py" in ranked["text"]


def test_load_rejects_unresolved_edges_with_a_road_sign(fake_repo, tmp_path):
    graph = _graph(fake_repo)
    graph["edges"][0]["target"] = "missing:node"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(graph), encoding="utf-8")

    with pytest.raises(codegraph.CodeGraphError) as error:
        codegraph.load(path)

    assert "references a missing node" in str(error.value)
    assert "artoo map schema" in str(error.value)


def test_cli_build_view_why_path_and_schema(fake_repo, tmp_path):
    _graph(fake_repo)
    graph_path = tmp_path / "graph.json"
    runner = CliRunner()

    built = runner.invoke(
        main, ["map", "build", str(fake_repo), "--out", str(graph_path), "--json"]
    )
    assert built.exit_code == 0, built.output
    receipt = json.loads(built.output)
    assert receipt["contract"] == codegraph.CONTRACT
    assert graph_path.is_file()

    viewed = runner.invoke(
        main,
        [
            "map",
            "view",
            str(graph_path),
            "--focus",
            "fakepkg.cli.main",
            "--direction",
            "outgoing",
            "--format",
            "mermaid",
        ],
    )
    assert viewed.exit_code == 0, viewed.output
    assert "flowchart LR" in viewed.output

    why = runner.invoke(main, ["map", "why", str(graph_path), "fakepkg.cli.main"])
    assert why.exit_code == 0, why.output
    assert "outgoing" in why.output and "calls" in why.output

    path = runner.invoke(
        main,
        [
            "map",
            "path",
            str(graph_path),
            "entrypoint:fake",
            "fakepkg.cli.helper",
        ],
    )
    assert path.exit_code == 0, path.output
    assert "invokes" in path.output and "calls" in path.output

    context = runner.invoke(
        main,
        [
            "map",
            "context",
            str(graph_path),
            "Where is helper called?",
            "--budget-tokens",
            "64",
            "--json",
        ],
    )
    assert context.exit_code == 0, context.output
    assert json.loads(context.output)["estimated_tokens"] <= 64

    schema = runner.invoke(main, ["map", "schema"])
    assert schema.exit_code == 0
    assert json.loads(schema.output)["title"] == "Artoo code graph"
