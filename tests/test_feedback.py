"""`artoo feedback`: route artifact-side feedback into the attached notebook."""

import json

from click.testing import CliRunner

from artoo.cli import main


def invoke(*args):
    return CliRunner().invoke(main, list(args))


def _breadcrumbs(artifact):
    f = artifact.dir / "work" / "feedback.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text().splitlines()]


def test_feedback_opens_question_with_cited_claim(notebook_artifact, flip_stub):
    flip_stub.set_ids(["C1", "A1"])
    result = invoke(
        "feedback", str(notebook_artifact.dir), "C1 overstates the effect", "--claim", "C1"
    )
    assert result.exit_code == 0, result.output
    assert "opened question Q1" in result.output

    # The routed question text carries the artifact ref and the cited id.
    questions = flip_stub.questions()
    assert len(questions) == 1
    assert "[C1]" in questions[0]
    assert notebook_artifact.slug in questions[0]
    assert "C1 overstates the effect" in questions[0]

    # A firewalled breadcrumb records the back-flow.
    crumbs = _breadcrumbs(notebook_artifact)
    assert len(crumbs) == 1
    assert crumbs[0]["ref"] == "C1"
    assert crumbs[0]["routed_as"] == "question:Q1"
    assert crumbs[0]["text"] == "C1 overstates the effect"


def test_feedback_without_citation(notebook_artifact, flip_stub):
    result = invoke("feedback", str(notebook_artifact.dir), "the intro reads oddly")
    assert result.exit_code == 0, result.output
    questions = flip_stub.questions()
    assert "the intro reads oddly" in questions[0]
    assert "on [" not in questions[0]  # no cited id
    assert _breadcrumbs(notebook_artifact)[0]["ref"] == ""


def test_feedback_as_log(notebook_artifact, flip_stub):
    flip_stub.set_ids(["A1"])
    result = invoke(
        "feedback", str(notebook_artifact.dir), "source A1 moved", "--source", "A1", "--as-log"
    )
    assert result.exit_code == 0, result.output
    assert "logged an event" in result.output
    assert flip_stub.logs() and "[A1]" in flip_stub.logs()[0]
    assert flip_stub.questions() == []  # routed to the log, not a question
    assert _breadcrumbs(notebook_artifact)[0]["routed_as"] == "log"


def test_feedback_refuses_unknown_id(notebook_artifact, flip_stub):
    flip_stub.set_ids(["C1"])  # C9 is not known
    result = invoke(
        "feedback", str(notebook_artifact.dir), "typo protection", "--claim", "C9"
    )
    assert result.exit_code != 0
    assert "C9 does not resolve" in result.output
    assert flip_stub.questions() == []  # nothing routed on refusal
    assert _breadcrumbs(notebook_artifact) == []


def test_feedback_refuses_both_claim_and_source(notebook_artifact, flip_stub):
    result = invoke(
        "feedback", str(notebook_artifact.dir), "x", "--claim", "C1", "--source", "A1"
    )
    assert result.exit_code != 0
    assert "at most one" in result.output


def test_feedback_no_notebook(artifact, flip_stub):
    result = invoke("feedback", str(artifact.dir), "no notebook here")
    assert result.exit_code != 0
    assert "no flip notebook is attached" in result.output


def test_feedback_absent_flip(notebook_artifact, monkeypatch, tmp_path):
    monkeypatch.delenv("ARTOO_FLIP_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    result = invoke("feedback", str(notebook_artifact.dir), "flip is gone")
    assert result.exit_code != 0
    assert "flip is not installed" in result.output
    assert _breadcrumbs(notebook_artifact) == []
