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


@pytest.mark.parametrize("with_lite", [True, False], ids=["from the Lite", "from scratch"])
def test_a_light_capture_is_a_padded_a2_lite(tmp_path, with_lite):
    import nam_lite
    rng = np.random.default_rng(4)
    full, lite = a2(8, rng, 0.3), a2(3, rng, 0.3)
    subs = [{"max_value": 0.5, "model": lite}, {"max_value": 1, "model": full}] if with_lite else [{"max_value": 1, "model": full}]
    path = tmp_path / "a2.nam"
    path.write_text(json.dumps({"architecture": "SlimmableContainer", "version": "0.7.0", "sample_rate": 48000,
                                "metadata": {"name": "test"}, "config": {"submodels": subs}}))
    out, before, after = nr.refine(str(path), 20, seconds=2.0, log=lambda s: None, lr=1e-3, segment=2048, layers=16)
    assert nam_pack.a2_mismatch(out["config"], 3) is None and len(out["weights"]) == 1871
    assert nam_lite.layer_count(out["weights"]) == 16
    assert out["metadata"]["nam_light"] == {"layers": 16, "of": 23} and out["metadata"]["name"] == "test [16 layers]"
    assert np.isfinite(after) and np.isfinite(before) == with_lite
    # the padded file plays as the 16-layer net it holds (to float rounding: torch picks conv paths by length)
    from nam.models import init_from_nam
    from nam.models._from_nam import _init_wavenet
    m = init_from_nam(out).eval()
    short = _init_wavenet(nr.prefix_config(out["config"], 16), 48000).eval()
    short.load_state_dict({k: v for k, v in m.state_dict().items() if k in short.state_dict()})
    short._net._head_scale = m._net._head_scale
    x = rng.normal(0, 0.1, 6000).astype(np.float32)
    torch.testing.assert_close(nr.run(m, x, torch)[-2000:], nr.run(short, x, torch)[-2000:], rtol=1e-5, atol=1e-6)


def test_a_file_with_another_loudness_offset_loads_with_a_warning():
    rng = np.random.default_rng(5)
    d = {"architecture": "SlimmableContainer", "version": "0.7.0", "sample_rate": 48000,
         "metadata": {"name": "t3k", "loudness": 99.0},
         "config": {"submodels": [{"max_value": 0.5, "model": a2(3, rng, 0.3)}, {"max_value": 1, "model": a2(8, rng, 0.3)}]}}
    c = nr.Capture(d)
    assert c.warning and abs(c.loudness + c.loud_offset - 99.0) < 1e-9
