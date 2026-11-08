"""The Helix LT build (helix-lt/lt_port.py) from the stock LT 3.80.0 .hxf and a checkout of the Floor
port at lt_port.FLOOR_PORT (point HELIX_LT_HXF and FLOOR_PORT at them). About 5 minutes: the Floor
port's own build runs, its KernelCheck included. The output's MD5 is pinned like the other units'."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = [pytest.mark.firmware, pytest.mark.slow]

BUILT_MD5 = "ecb8d773333a6cd2b81545e8a6542cce"   # not run on an LT


def test_build(tmp_path):
    stock, port = os.environ.get("HELIX_LT_HXF"), os.environ.get("FLOOR_PORT")
    if not (stock and port):
        pytest.skip("HELIX_LT_HXF and FLOOR_PORT are not set")
    out = tmp_path / "lt.hxf"
    r = subprocess.run([sys.executable, str(ROOT / "helix-lt" / "lt_port.py"), port, stock, "-o", str(out),
                        "--work", str(tmp_path / "lt_port")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL OK" in r.stdout and "round-trips byte for byte" in r.stdout
    assert hashlib.md5(out.read_bytes()).hexdigest() == BUILT_MD5
