"""Private review is bound to a render and kept outside the served tree."""

import json

from click.testing import CliRunner

from artoo.cli import main


def _events(artifact):
    path = artifact.dir / "work" / "reviews.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_finding_and_resolution_name_their_distinct_site_revisions(artifact):
    page = artifact.site_dir / "index.html"
    original = page.read_bytes()
    runner = CliRunner()
    result = runner.invoke(
        main, ["review", str(artifact.dir), "The title obscures the task", "--page", "index.html"]
    )
    assert result.exit_code == 0, result.output
    first = _events(artifact)[0]
    assert first["schema"] == "artoo-review/1"
    assert first["event"] == "finding"
    assert first["page"] == "index.html"
    assert first["git_head"] == ""  # fixture is not in a repository
    assert page.read_bytes() == original

    page.write_text(page.read_text() + "\n<!-- revised -->\n")
    resolved = runner.invoke(
        main,
        ["review", str(artifact.dir), "Title now names the task", "--page", "index.html",
         "--resolves", first["id"]],
    )
    assert resolved.exit_code == 0, resolved.output
    second = _events(artifact)[1]
    assert second["event"] == "resolution"
    assert second["resolves"] == first["id"]
    assert second["site_revision"] != first["site_revision"]
    assert not (artifact.site_dir / "work" / "reviews.jsonl").exists()


def test_review_refuses_missing_page_unknown_or_closed_finding(artifact):
    runner = CliRunner()
    bad_page = runner.invoke(
        main, ["review", str(artifact.dir), "x", "--page", "../secret.md"]
    )
    assert bad_page.exit_code != 0
    assert "--page" in bad_page.output
    unknown = runner.invoke(main, ["review", str(artifact.dir), "x", "--resolves", "missing"])
    assert unknown.exit_code != 0
    assert not (artifact.dir / "work" / "reviews.jsonl").exists()

    runner.invoke(main, ["review", str(artifact.dir), "finding"])
    found = _events(artifact)[0]
    runner.invoke(main, ["review", str(artifact.dir), "fixed", "--resolves", found["id"]])
    duplicate = runner.invoke(
        main, ["review", str(artifact.dir), "fixed again", "--resolves", found["id"]]
    )
    assert duplicate.exit_code != 0
    assert len(_events(artifact)) == 2
