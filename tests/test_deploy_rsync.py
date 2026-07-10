from pathlib import Path

from artoo.deploy import rsync
from artoo.deploy.base import DeployContext
from artoo.deploy.rsync import RsyncDeployer


def test_build_command_shape(tmp_path):
    target = {"host": "h.example.com", "user": "deploy", "path": "/var/www/site/"}
    cmd = rsync.build_command(target, tmp_path, "reports/q3", dry_run=True)
    assert cmd[0] == "rsync"
    assert "--dry-run" in cmd
    assert "--mkpath" in cmd
    assert cmd[-1] == "deploy@h.example.com:/var/www/site/reports/q3/"
    assert cmd[-2] == f"{tmp_path}/"


def test_build_command_key_and_port(tmp_path):
    target = {
        "host": "h", "user": "u", "path": "/srv",
        "ssh_key": "~/.ssh/k", "port": 2222,
    }
    cmd = rsync.build_command(target, tmp_path, "", dry_run=False)
    ssh = cmd[cmd.index("-e") + 1]
    assert "-i" in ssh and "-p 2222" in ssh
    assert str(Path("~/.ssh/k").expanduser()) in ssh


def test_targets_repo_overrides_user(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    user_conf = tmp_path / "xdg" / "artoo"
    user_conf.mkdir(parents=True)
    (user_conf / "targets.toml").write_text(
        '[targets.public]\nhost = "user-level"\nuser = "u"\npath = "/a"\n'
        '[targets.only-user]\nhost = "x"\nuser = "u"\npath = "/b"\n'
    )
    repo = tmp_path / "repo"
    (repo / ".artoo").mkdir(parents=True)
    (repo / ".artoo" / "targets.toml").write_text(
        '[targets.public]\nhost = "repo-level"\nuser = "u"\npath = "/a"\n'
    )
    targets = rsync.load_targets(repo)
    assert targets["public"]["host"] == "repo-level"
    assert targets["only-user"]["host"] == "x"


def test_deploy_unknown_target(artifact, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))
    ctx = DeployContext(
        manifest=artifact, staged=tmp_path, config={"target": "nope"}, dry_run=True
    )
    result = RsyncDeployer().deploy(ctx)
    assert not result.ok
    assert "nope" in result.message
