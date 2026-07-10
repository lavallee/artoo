import subprocess

import pytest

from artoo import manifest as manifest_mod
from artoo import scaffold


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
