import os

from click.testing import CliRunner

from artoo.cli import main


def _fake_vizier(tmp_path, monkeypatch, body: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "vizier"
    executable.write_text("#!/bin/sh\n" + body)
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return executable


def test_vizier_guide_forwards_arguments_and_writes_complete_private_receipt(
    artifact, tmp_path, monkeypatch
):
    args_file = tmp_path / "args.txt"
    monkeypatch.setenv("FAKE_VIZIER_ARGS", str(args_file))
    executable = _fake_vizier(
        tmp_path,
        monkeypatch,
        'printf "%s\\n" "$@" > "$FAKE_VIZIER_ARGS"\n'
        "printf 'guidance first line\\nguidance final line\\n'\n"
        "printf 'local corpus note\\n' >&2\n",
    )

    result = CliRunner().invoke(
        main,
        [
            "vizier-guide",
            "compare district spending",
            "--context",
            "headline and source context",
            "--family",
            "Change over time",
            "--series-count",
            "4",
            "--form-count",
            "3",
            "--prior-count",
            "2",
            "--semantic",
            "--artifact",
            str(artifact.dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "work/vizier-guidance.md" in result.output
    assert args_file.read_text().splitlines() == [
        "guide",
        "compare district spending",
        "--context",
        "headline and source context",
        "--family",
        "Change over time",
        "--n-series",
        "4",
        "--forms",
        "3",
        "--prior",
        "2",
        "--semantic",
    ]

    receipt_path = artifact.dir / "work" / "vizier-guidance.md"
    receipt = receipt_path.read_text()
    assert f"- Executable: `{executable}`" in receipt
    assert "- Exit status: `0`" in receipt
    assert "vizier guide 'compare district spending'" in receipt
    assert "guidance first line\nguidance final line\n" in receipt
    assert "local corpus note\n" in receipt
    assert not (artifact.site_dir / "vizier-guidance.md").exists()


def test_vizier_guide_forwards_explicit_no_semantic(artifact, tmp_path, monkeypatch):
    args_file = tmp_path / "args.txt"
    monkeypatch.setenv("FAKE_VIZIER_ARGS", str(args_file))
    _fake_vizier(
        tmp_path,
        monkeypatch,
        'printf "%s\\n" "$@" > "$FAKE_VIZIER_ARGS"\nprintf "ok\\n"\n',
    )

    result = CliRunner().invoke(
        main,
        ["vizier-guide", "rank values", "--no-semantic", "--artifact", str(artifact.dir)],
    )
    assert result.exit_code == 0, result.output
    assert args_file.read_text().splitlines() == ["guide", "rank values", "--no-semantic"]


def test_vizier_guide_nonzero_is_actionable_and_writes_no_partial_receipt(
    artifact, tmp_path, monkeypatch
):
    _fake_vizier(
        tmp_path,
        monkeypatch,
        "printf 'bad family or local data\\n' >&2\nexit 9\n",
    )

    result = CliRunner().invoke(
        main,
        ["vizier-guide", "compare values", "--artifact", str(artifact.dir)],
    )
    assert result.exit_code != 0
    assert "exited with status 9" in result.output
    assert "Run the command directly" in result.output
    assert "bad family or local data" in result.output
    assert "No receipt was written" in result.output
    assert not (artifact.dir / "work" / "vizier-guidance.md").exists()
    assert not list((artifact.dir / "work").glob("*vizier-guidance*.tmp"))


def test_vizier_guide_missing_tool_is_actionable_and_writes_no_receipt(
    artifact, tmp_path, monkeypatch
):
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))

    result = CliRunner().invoke(
        main,
        ["vizier-guide", "compare values", "--artifact", str(artifact.dir)],
    )
    assert result.exit_code != 0
    assert "not available on PATH" in result.output
    assert "uv tool install datavizier" in result.output
    assert "No receipt was written" in result.output
    assert not (artifact.dir / "work" / "vizier-guidance.md").exists()
