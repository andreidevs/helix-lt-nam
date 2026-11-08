"""tools/nam_refine.py on a made-up A2 container (no capture in the repo): the Lite comes out the A2 Lite
shape, never worse than it went in, and loads in nam2ir. Needs torch and neural-amp-modeler."""
import json

import numpy as np
import pytest

import nam_pack

pytestmark = pytest.mark.slow
try:
    import torch  # noqa: F401
    import nam  # noqa: F401
except ImportError as e:        # not installed, or installed but not loadable here
    pytest.skip(f"torch and neural-amp-modeler: {e}", allow_module_level=True)
import nam_refine as nr  # noqa: E402


def a2(channels, rng, scale):
    cfg = nr.lite_config()
    cfg["layers"][0].update(channels=channels, bottleneck=channels)
    c, n = channels, len(nam_pack.KERNEL)
    count = c + sum(c * c * k + c + c + c * c + c for k in nam_pack.KERNEL) + c * nam_pack.HEAD_TAPS + 2
    assert n == 23
    return {"version": "0.7.0", "architecture": "WaveNet", "config": cfg, "sample_rate": 48000,
            "weights": list(rng.normal(0, scale, count))}


def test_refine_keeps_the_lite_shape_and_never_does_worse(tmp_path):
    rng = np.random.default_rng(1)
    full, lite = a2(8, rng, 0.3), a2(3, rng, 0.3)
    path = tmp_path / "a2.nam"
    path.write_text(json.dumps({"architecture": "SlimmableContainer", "version": "0.7.0", "sample_rate": 48000,
                                "metadata": {"name": "test", "input_level_dbu": 12.0},
                                "config": {"submodels": [{"max_value": 0.5, "model": lite},
                                                         {"max_value": 1, "model": full}]}}))
    out, before, after = nr.refine(str(path), 30, seconds=2.0, log=lambda s: None, lr=1e-3, segment=2048)
    assert after <= before
    assert nam_pack.a2_mismatch(out["config"], 3) is None and len(out["weights"]) == 1871
    assert out["weights"] != lite["weights"] or after == before
    assert out["metadata"]["input_level_dbu"] == 12.0 and np.isfinite(out["metadata"]["loudness"])
    p = tmp_path / "hd.nam"
    p.write_text(json.dumps(out))
    w, c = nam_pack.load(str(p))
    assert c == 3 and len(w) == 1871


def test_chain_gains_follow_the_cables_and_the_trims():
    class C:
        def __init__(self, dbu, out_dbu):
            self.dbu, self.out_dbu = dbu, out_dbu
    pedal, amp, bare = C(12.0, 18.0), C(6.0, None), C(None, None)
    g = nr.chain_gains([pedal, amp], [0.0, 0.0])
    assert g[0] == 1.0 and abs(20 * np.log10(g[1]) - 12.0) < 1e-9        # +18 dBu out into a 6 dBu input
    g = nr.chain_gains([pedal, amp, bare], [3.0, -2.0, 0.0])
    assert [round(20 * np.log10(v), 9) for v in g] == [3.0, 10.0, 0.0]   # unity where a capture doesn't say


def test_a_chain_trains_into_one_lite(tmp_path):
    rng = np.random.default_rng(3)
    caps = []
    for k in range(2):
        d = {"architecture": "SlimmableContainer", "version": "0.7.0", "sample_rate": 48000,
             "metadata": {"name": f"stage{k}", "input_level_dbu": 10.0, "output_level_dbu": 10.0},
             "config": {"submodels": [{"max_value": 0.5, "model": a2(3, rng, 0.3)},
                                      {"max_value": 1, "model": a2(8, rng, 0.3)}]}}
        caps.append(nr.Capture(d))
    out, before, after = nr.distil(caps, [0.0, 0.0], 20, seconds=2.0, log=lambda s: None, lr=1e-3,
                                   segment=2048, chain=True, name="chain")
    assert after <= before and nam_pack.a2_mismatch(out["config"], 3) is None
    assert [s["name"] for s in out["metadata"]["nam_chain"]] == ["stage0", "stage1"]
    assert out["metadata"]["input_level_dbu"] == 10.0 and out["metadata"]["name"] == "chain"


def test_a_lite_only_capture_is_refused(tmp_path):
    p = tmp_path / "lite.nam"
    p.write_text(json.dumps(a2(3, np.random.default_rng(2), 0.1)))
    with pytest.raises(SystemExit, match="no bigger model"):
        nr.models(json.loads(p.read_text()))
