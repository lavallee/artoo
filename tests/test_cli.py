from click.testing import CliRunner

from artoo.cli import main


def invoke(*args):
    return CliRunner().invoke(main, list(args))


def test_version():
    result = invoke("--version")
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init_and_status(tmp_path):
    result = invoke("init", str(tmp_path / "art"), "--kind", "note", "--title", "A note")
    assert result.exit_code == 0, result.output
    result = invoke("status", str(tmp_path / "art"))
    assert result.exit_code == 0
    assert "manifest and firewall clean" in result.output


def test_init_refuses_existing(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("init", str(tmp_path / "art"))
    assert result.exit_code != 0


def test_list(tmp_path):
    invoke("init", str(tmp_path / "one"), "--kind", "note")
    invoke("init", str(tmp_path / "two"), "--kind", "report")
    result = invoke("list", str(tmp_path))
    assert "one" in result.output and "two" in result.output


def test_build(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("build", str(tmp_path / "art"))
    assert result.exit_code == 0
    assert "site ready" in result.output


def test_deploy_requires_target(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("deploy", str(tmp_path / "art"))
    assert result.exit_code != 0
    assert "no [deploy] target" in result.output


def test_doctor(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("doctor", str(tmp_path))
    assert result.exit_code == 0
    assert "1/1 artifacts clean" in result.output


def test_generate_lists_generators():
    result = invoke("generate", "--help")
    assert "explainer" in result.output


def test_lib_flow(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("lib", "status", "--artifact", str(tmp_path / "art"))
    assert "artoo-kit" in result.output and "intact" in result.output
    result = invoke("lib", "update", "artoo-kit", "--artifact", str(tmp_path / "art"))
    assert result.exit_code == 0
