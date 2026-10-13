"""Exercise the actual vendored JavaScript protocol without npm dependencies."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_store_client_protocol():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the vendored JavaScript protocol tests")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [node, "--test", "tests/test_store_client.cjs"], cwd=root, check=True, timeout=30
    )
