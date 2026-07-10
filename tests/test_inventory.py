from artoo.generators.explainer import inventory


def test_take_inventory(fake_repo):
    inv = inventory.take_inventory(fake_repo)
    assert inv["name"] == "fake-repo"
    assert inv["readme"]["title"] == "fake-repo"
    assert "frobnicates" in inv["readme"]["first_paragraph"]
    assert inv["python"]["packages"][0]["name"] == "fakepkg"
    assert inv["python"]["packages"][0]["scripts"] == ["fake"]
    assert inv["python"]["source_loc"] > 0
    assert inv["python"]["test_files"] == 1
    module_paths = {m["path"] for m in inv["python"]["modules"]}
    assert "src/fakepkg/cli.py" in module_paths


def test_docstrings_and_imports(fake_repo):
    inv = inventory.take_inventory(fake_repo)
    cli = next(m for m in inv["python"]["modules"] if m["path"] == "src/fakepkg/cli.py")
    assert cli["doc"] == "CLI for fakepkg."
    assert "fakepkg" in cli["imports"]


def test_units(fake_repo):
    inv = inventory.take_inventory(fake_repo)
    units = inventory.analysis_units(inv)
    names = {u["name"] for u in units}
    assert "src" in names or "src/fakepkg" in names
    assert "root" in names  # README + pyproject
    assert all(u["files"] for u in units)


def test_exclude(fake_repo):
    (fake_repo / "site" / "explainer").mkdir(parents=True)
    (fake_repo / "site" / "explainer" / "big.html").write_text("<html>\n" * 500)
    inv = inventory.take_inventory(fake_repo, exclude=("site/explainer/",))
    assert not any(f["path"].startswith("site/explainer") for f in inv["files"])


def test_cache(fake_repo, tmp_path):
    work = tmp_path / "work"
    inv1 = inventory.load_or_take(fake_repo, work)
    (fake_repo / "new.py").write_text("x = 1\n")
    inv2 = inventory.load_or_take(fake_repo, work)
    assert inv1["files"] == inv2["files"]  # cached
    inv3 = inventory.load_or_take(fake_repo, work, fresh=True)
    assert len(inv3["files"]) == len(inv2["files"]) + 1
