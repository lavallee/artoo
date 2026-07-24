import json
import subprocess
import textwrap

import pytest

from artoo import manifest as manifest_mod
from artoo import scaffold

# A representative flip-render/1 projection (the shape `flip export json` emits),
# used by the stub and asserted against across the provenance tests.
SAMPLE_PROJECTION = {
    "contract": "flip-render/1",
    "generated": "2026-07-24T16:00:00Z",
    "source_trail_public": True,
    "notebook": {
        "uid": "nb-abc123",
        "slug": "demo-nb",
        "title": "Demo notebook",
        "kind": "scout",
        "status": "active",
        "created": "2026-07-20",
        "updated": "2026-07-24",
        "visibility": "public",
    },
    "sources": [
        {"id": "A1", "slug": "paper", "kind": "paper", "grade": "A",
         "independence": "original", "freshness": "fresh", "title": "Latency paper",
         "canonical_url": "https://example.com/paper", "captured_at": "2026-07-24T16:00:00Z",
         "sha256": "deadbeef"},
        {"id": "A2", "slug": "data", "kind": "dataset", "grade": "B",
         "independence": "original", "freshness": "fresh", "title": "Throughput dataset",
         "canonical_url": "", "captured_at": "2026-07-24T16:00:00Z", "sha256": "cafef00d"},
    ],
    "claims": [
        {"id": "C1", "slug": "latency", "text": "The system reduces latency by 40%.",
         "status": "verified", "load_bearing": True, "sources": ["A1"], "corroboration": 1,
         "verifications": [{"method": "recomputation", "by": "agent:claude", "date": "2026-07-24"}]},
        {"id": "C2", "slug": "throughput", "text": "Throughput scales to 8 cores.",
         "status": "asserted", "load_bearing": False, "sources": ["A2"], "corroboration": 1,
         "verifications": []},
    ],
    "questions": [],
    "decisions": [],
    "sessions": [],
    "log_tail": [],
}


class _FlipStub:
    """Controller over a fake `flip` CLI installed via ARTOO_FLIP_BIN."""

    def __init__(self, responses_dir):
        self.dir = responses_dir

    def set_export(self, data):
        (self.dir / "export.json").write_text(json.dumps(data), encoding="utf-8")

    def refuse_export(self, message="notebook visibility is 'internal'; set visibility: public"):
        (self.dir / "export.json").unlink(missing_ok=True)
        (self.dir / "export.err").write_text(message, encoding="utf-8")

    def set_doctor(self, findings):
        (self.dir / "doctor.json").write_text(json.dumps(findings), encoding="utf-8")


@pytest.fixture
def flip_stub(tmp_path, monkeypatch):
    """Install a hermetic fake `flip` on ARTOO_FLIP_BIN; return its controller."""
    root = tmp_path / "flipstub"
    responses = root / "responses"
    responses.mkdir(parents=True)
    script = root / "flip"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json, pathlib, sys
            R = pathlib.Path({str(responses)!r})
            args = sys.argv[1:]
            if "export" in args and "json" in args:
                f = R / "export.json"
                if not f.exists():
                    err = R / "export.err"
                    sys.stderr.write(err.read_text() if err.exists() else "refused")
                    sys.exit(1)
                sys.stdout.write(f.read_text()); sys.exit(0)
            if "doctor" in args:
                f = R / "doctor.json"
                data = json.loads(f.read_text()) if f.exists() else []
                sys.stdout.write(json.dumps(data))
                sys.exit(1 if any(x.get("level") == "ERROR" for x in data) else 0)
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("ARTOO_FLIP_BIN", str(script))
    return _FlipStub(responses)


@pytest.fixture
def notebook_artifact(artifact):
    """A scaffolded artifact with an attached (fake) flip notebook root."""
    nb = artifact.dir / "notebook"
    nb.mkdir()
    (nb / "index.md").write_text(
        "---\nokf_version: '0.1'\nflip: '0.6'\nslug: demo-nb\nuid: nb-abc123\n"
        "title: Demo notebook\nkind: scout\nstatus: active\ncreated: '2026-07-20'\n"
        "updated: '2026-07-24'\nvisibility: public\n---\n\n# Demo notebook\n",
        encoding="utf-8",
    )
    artifact.notebook = "notebook"
    artifact.save()
    return artifact


@pytest.fixture
def fake_repo(tmp_path):
    """A tiny python repo: README, pyproject, src package, tests."""
    repo = tmp_path / "fake-repo"
    (repo / "src" / "fakepkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "README.md").write_text(
        "# fake-repo\n\nA tiny fake project. It parses widgets and frobnicates them.\n"
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "fakepkg"\nversion = "0.1.0"\n'
        'description = "widget frobnicator"\ndependencies = ["click"]\n'
        "[project.scripts]\nfake = \"fakepkg.cli:main\"\n"
    )
    (repo / "src" / "fakepkg" / "__init__.py").write_text(
        '"""Fake package: frobnicates widgets."""\n__version__ = "0.1.0"\n'
    )
    (repo / "src" / "fakepkg" / "cli.py").write_text(
        '"""CLI for fakepkg."""\nimport fakepkg\n\n\ndef main():\n'
        "    print(fakepkg.__version__)\n"
    )
    (repo / "tests" / "test_cli.py").write_text(
        "from fakepkg import cli\n\n\ndef test_main():\n    cli.main()\n"
    )
    return repo


@pytest.fixture
def git_repo(fake_repo):
    """fake_repo, committed, with a GitHub-shaped origin remote."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-qm", "init", "--allow-empty"],
        cwd=fake_repo, check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-qm", "files"],
        cwd=fake_repo, check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:someone/fake-repo.git"],
        cwd=fake_repo, check=True,
    )
    return fake_repo


@pytest.fixture
def artifact(tmp_path):
    """A freshly scaffolded artifact with the kit vendored."""
    return scaffold.init_artifact(
        tmp_path / "my-report", title="My report", kind="report",
        description="a test artifact",
    )


@pytest.fixture(autouse=True)
def _no_workers(monkeypatch):
    """Tests never shell out to agent CLIs."""
    monkeypatch.setenv("ARTOO_WORKERS_DISABLED", "1")


@pytest.fixture
def load(artifact):
    def _load():
        return manifest_mod.load(artifact.dir)

    return _load
