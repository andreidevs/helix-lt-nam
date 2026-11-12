#!/usr/bin/env python3
"""nam_refine.py - a closer A2 Lite of a capture, trained against the capture's own bigger model.

A TONE3000 "A2" .nam holds two sizes of one capture: the A2 Full (8 channels, 12,146 weights) and
the A2 Lite (3 channels, 1,871 weights) that the HX Stomp and Helix kernels run. The Lite misses the
Full by a percent or so. This trains the Lite further against the Full (distillation): the Full plays
the teacher on any input, so no reamping and no hardware are needed, and the result is the same Lite
shape, the same DSP cost. A capture with no Lite inside (a standard WaveNet, any NAM architecture) is
the teacher for a Lite trained from scratch.

Input: synthetic guitar (plucked strings, chords, palm mutes, at many levels), NAM's loudness signal,
and any DI recordings given with --di (better: real playing). The error is ESR against the teacher on
a held-out part, before and after; the best weights seen are kept, so a refine never comes out worse
than the Lite it started from.

--layers P (default 23, all) trains a light capture instead: only the Lite's first P layers, the rest
of the file's layers all zero (a zero layer adds exactly 0, so the file plays as the P-layer net and is
still an ordinary A2 Lite; nam2ir writes P into the User IR so a firmware can skip the zero layers). It
starts from the capture's own Lite's first P layers (from scratch without a Lite); its error before is
the full Lite's.

usage: nam_refine.py in.nam [-o out.nam] [--quick | --deep | --steps N] [--di guitar.wav ...]
                            [--seconds 90] [--seed 0] [--layers 23]
Writes an A2 Lite .nam (default: "<name> HD Lite.nam" next to the input, "<name> [P layers].nam" for a
light one), loudness re-measured, the capture's metadata kept; tools/nam2ir.py converts it for the unit.
Needs torch and neural-amp-modeler.
"""
import argparse
import copy
import json
import math
import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sharc"))
import nam_pack  # noqa: E402

RATE = 48000
STEPS = {"quick": 800, "standard": 3000, "deep": 10000}
SEGMENT, BATCH = 4096, 16
PRE_EMPH = 0.85          # the NAM trainer's pre-emphasis, for an optional high-end term (pre_emph=, off by default)


def lite_config():
    """The A2 Lite WaveNet config, as TONE3000's A2 files carry it (nam_pack.a2_mismatch passes it)."""
    off = {"shift": True, "active": False, "groups": 1}
    n = len(nam_pack.KERNEL)
    layer = {"head": {"bias": True, "kernel_size": nam_pack.HEAD_TAPS, "out_channels": 1},
             "head1x1": {"active": False, "groups": 1, "out_channels": 1}, "channels": 3,
             "layer1x1": {"active": True, "groups": 1}, "dilations": list(nam_pack.DILATION), "slimmable": None,
             "activation": [{"type": "LeakyReLU", "negative_slope": 0.01}] * n, "bottleneck": 3, "input_size": 1,
             "gating_mode": ["none"] * n, "groups_input": 1, "kernel_sizes": list(nam_pack.KERNEL),
             "condition_size": 1, "groups_input_mixin": 1, "secondary_activation": [None] * n}
    for k in ("conv_pre_film", "conv_post_film", "head1x1_post_film", "layer1x1_post_film", "activation_pre_film",
              "activation_post_film", "input_mixin_pre_film", "input_mixin_post_film"):
        layer[k] = dict(off)
    return {"head": None, "layers": [layer], "head_scale": 0.02}


def prefix_config(cfg, layers):
    """An A2 Lite config cut to its first `layers` layers (the capture's own: head_scale differs)."""
    cfg = copy.deepcopy(cfg)
    la = cfg["layers"][0]
    for key in ("dilations", "kernel_sizes", "activation", "gating_mode", "secondary_activation"):
        if isinstance(la.get(key), list):
            la[key] = la[key][:layers]
    return cfg


def padded(student, full):
    """The full 23-layer model `full` holding the prefix net `student`: its layers in their places, every
    later layer's tensors zero (a zero layer leaves the residual stream and the head sum unchanged)."""
    import torch
    src = student.state_dict()
    full.load_state_dict({k: src[k] if k in src else torch.zeros_like(v) for k, v in full.state_dict().items()})
    full._net._head_scale = student._net._head_scale       # a float, not in the state dict
    return full


def models(d):
    """(teacher, lite) model dicts of a .nam: the biggest model and the A2 Lite inside a container, or
    the file's own model and None (a Lite then comes from scratch)."""
    if d.get("architecture") == "SlimmableContainer":
        subs = [dict(s["model"], sample_rate=s["model"].get("sample_rate", d.get("sample_rate"))) for s in d["config"]["submodels"]]
    else:
        subs = [d]
    lites = [m for m in subs if m.get("architecture") == "WaveNet" and nam_pack.a2_mismatch(m["config"], 3) is None]
    teacher = max(subs, key=lambda m: len(m.get("weights", [])))
    if lites and teacher is lites[0]:
        raise SystemExit("this capture is an A2 Lite only: no bigger model to learn from")
    rate = teacher.get("sample_rate") or RATE
    if rate != RATE:
        raise SystemExit(f"a {rate:g} Hz capture; the units run at 48 kHz")
    return teacher, (lites[0] if lites else None)


# ------------------------------------------------------------------ input signals
def synth_guitar(seconds, rng):
    """Plucked-string guitar (Karplus-Strong), single notes, chords and palm mutes, at levels from
    soft picking to hard strumming (peaks 0.02..0.6), with gaps; the low strings to the high frets."""
    out = np.zeros(int(seconds * RATE), np.float32)
    t = 0
    while t < len(out) - RATE // 4:
        kind = rng.choice(["note", "chord", "mute"], p=[0.45, 0.4, 0.15])
        dur = int(RATE * (rng.uniform(0.08, 0.25) if kind == "mute" else rng.uniform(0.4, 2.5)))
        dur = min(dur, len(out) - t)
        base = 82.41 * 2 ** (rng.integers(0, 22) / 12)
        freqs = [base] if kind != "chord" else [base * 2 ** (i / 12) for i in (0, 7, 12, 16, 19, 24)[:rng.integers(3, 7)]]
        x = np.zeros(dur, np.float32)
        for k, f in enumerate(freqs):
            n = max(2, int(RATE / f))
            buf = rng.uniform(-1, 1, n).astype(np.float32)
            buf = np.convolve(buf, np.ones(rng.integers(1, 4)) / 3, "same").astype(np.float32)   # pick hardness
            decay = 0.996 if kind != "mute" else 0.97
            periods = []
            for _ in range(dur // n + 1):        # one string period at a time: the averaging lowpass, decaying
                periods.append(buf.copy())
                buf = decay * 0.5 * (buf + np.roll(buf, -1))
            y = np.concatenate(periods)[:dur]
            start = int(k * RATE * rng.uniform(0.005, 0.02)) if kind == "chord" else 0            # a strum
            x[start:] += y[:dur - start]
        x *= rng.uniform(0.02, 0.6) / (np.max(np.abs(x)) + 1e-9)
        out[t:t + dur] += x
        t += dur + int(RATE * rng.uniform(0.0, 0.3))
    return out


def read_wav(path):
    with wave.open(path, "rb") as w:
        if w.getframerate() != RATE:
            raise SystemExit(f"{path}: {w.getframerate()} Hz, not 48 kHz")
        width, ch, raw = w.getsampwidth(), w.getnchannels(), w.readframes(w.getnframes())
    if width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = ((b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16) ^ 0x800000) - 0x800000
    elif width in (2, 4):
        x = np.frombuffer(raw, "<i2" if width == 2 else "<i4")
    else:
        raise SystemExit(f"{path}: {8 * width}-bit samples")
    return (x.reshape(-1, ch)[:, 0] / float(1 << (8 * width - 1))).astype(np.float32)


def signals(seconds, seed, di_paths):
    """(train, held-out) inputs: synthetic guitar, NAM's loudness signal, and the DI files split 80/20."""
    rng = np.random.default_rng(seed)
    import nam.models as nm
    loud = read_wav(os.path.join(os.path.dirname(nm.__file__), "_resources", "loudness_input.wav"))
    di = [read_wav(p) for p in di_paths]
    cut = [int(len(x) * 0.8) for x in di]
    train = np.concatenate([synth_guitar(seconds, rng), loud] + [x[:c] for x, c in zip(di, cut)])
    held = np.concatenate([synth_guitar(max(10.0, seconds / 6), np.random.default_rng(seed + 1))] +
                          [x[c:] for x, c in zip(di, cut)])
    return train, held


# ------------------------------------------------------------------ training
def run(model, x, torch, chunk=1 << 19):
    """The model's output for all of x, aligned sample for sample (zeros before the start)."""
    rf = model.receptive_field
    xp = torch.cat([torch.zeros(rf - 1), torch.as_tensor(x)])
    out = []
    with torch.no_grad():
        for s in range(0, len(x), chunk):
            out.append(model(xp[s: s + chunk + rf - 1], pad_start=False))
    return torch.cat(out)


class Capture:
    """A .nam file's teacher (its biggest model, as a torch module) and its A2 Lite (a dict, or None)."""

    def __init__(self, d, name="capture"):
        from nam.models import init_from_nam
        self.d, self.name = d, (d.get("metadata") or {}).get("name") or name
        self.teacher_dict, self.lite = models(d)
        self.teacher = init_from_nam(upgrade(self.teacher_dict)).eval()
        meta = d.get("metadata") or {}
        self.dbu = nam_pack_number(meta.get("input_level_dbu"))
        self.out_dbu = nam_pack_number(meta.get("output_level_dbu"))
        self.loudness = nam_pack_number(meta.get("loudness"))
        self.loud_offset, self.warning = 0.0, None
        if self.loudness is not None:      # the file's loudness is its big model's: a check that it loaded right
            got = self.teacher._metadata_loudness()
            if abs(got - self.loudness) > 1.0:
                # some TONE3000 files measure another way (their Full and Lite agree with each other): go on
                # with the measured loudness, and give a result the file's offset so it plays as the file does
                self.warning = (f"warning: {self.name}: the model plays at {got:.1f} dB, its file says "
                                f"{self.loudness:.1f} dB; keeping the file's offset")
                self.loud_offset, self.loudness = self.loudness - got, got

    def kind(self):
        t = self.teacher_dict
        c = t["config"]["layers"][0].get("channels") if t.get("architecture") == "WaveNet" else None
        size = f"{t['architecture']} {c} ch" if c else t["architecture"]
        return f"A2 (Full + Lite)" if self.lite else f"{size}, {len(t['weights'])} weights (no Lite inside)"


def upgrade(m):
    """A model dict the NAM trainer of today reads: files from NAM 0.5 give each layer array's head as
    head_size and head_bias (a 1x1 rechannel), where newer ones have a head object."""
    m = copy.deepcopy(m)
    for la in (m.get("config") or {}).get("layers") or []:
        if "head" not in la and "head_size" in la:
            la["head"] = {"out_channels": la.pop("head_size"), "kernel_size": 1, "bias": la.pop("head_bias", False)}
    return m


def nam_pack_number(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def mix_gains(caps, levels):
    """(input gain, output gain) per capture for a blend: each driven as its own interface would be at
    the first capture's interface level (input_level_dbu), each output brought to -18 dB loudness, then
    weighted by its level (the weights summing to 1). One capture at level 1: (1, 1), as it is."""
    if len(caps) == 1:
        return [(1.0, 1.0)]
    ref = next((c.dbu for c in caps if c.dbu is not None), None)
    total = sum(levels) or 1.0
    out = []
    for c, lv in zip(caps, levels):
        g_in = 10 ** ((ref - c.dbu) / 20) if ref is not None and c.dbu is not None else 1.0
        g_out = 10 ** ((-18.0 - c.loudness) / 20) if c.loudness is not None else 1.0
        out.append((g_in, g_out * lv / total))
    return out


def target(caps, gains, x, torch, lags=None):
    """The blend's output for x: the sum of each teacher on its trimmed input, each delayed by its lag."""
    y = 0
    for k, (c, (gi, go)) in enumerate(zip(caps, gains)):
        yk = run(c.teacher, x * gi, torch) * go
        if lags and lags[k]:
            yk = torch.cat([torch.zeros(lags[k]), yk[:-lags[k]]])
        y = y + yk
    return y


def align(caps, gains, x, torch, max_lag=48):
    """Delays (samples) that line every capture up with the latest one, by cross-correlation, so their
    outputs add instead of cancelling (captures can differ by a few samples of latency)."""
    if len(caps) < 2:
        return [0] * len(caps)
    ys = [run(c.teacher, x * gi, torch).numpy() for c, (gi, _) in zip(caps, gains)]
    rel = [0]
    n = 1 << int(np.ceil(np.log2(2 * len(x))))
    f0 = np.fft.rfft(ys[0], n)
    for y in ys[1:]:
        cc = np.fft.irfft(np.fft.rfft(y, n) * np.conj(f0), n)
        win = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])
        rel.append(int(np.argmax(np.abs(win))) - max_lag)    # y lags the first capture by this
    top = max(rel)
    return [top - r for r in rel]


def chain_gains(caps, trims_db):
    """The gain into each stage of a chain (pedals, then the amp), as the cables would give it: one
    stage's output level in dBu (its capture's output_level_dbu) into the next one's input
    (input_level_dbu); unity where a capture doesn't say. trims_db adds a trim before each stage, the
    first one included (more drive into a pedal, or a hotter pedal into the amp)."""
    g = []
    for k, c in enumerate(caps):
        cable = 0.0
        if k and caps[k - 1].out_dbu is not None and c.dbu is not None:
            cable = caps[k - 1].out_dbu - c.dbu
        g.append(10 ** ((cable + trims_db[k]) / 20))
    return g


def chain_target(caps, gains, x, torch):
    """The chain's output for x: each stage on the previous one's output, through its gain."""
    y = torch.as_tensor(x)
    for c, g in zip(caps, gains):
        y = run(c.teacher, (y * g).numpy(), torch)
    return y


def rig_output(caps, params, x, torch, chain=False):
    """What the rig plays for x: a chain (params: trims in dB) or a blend (params: levels)."""
    if chain:
        return chain_target(caps, chain_gains(caps, params), x, torch)
    gains = mix_gains(caps, params)
    return target(caps, gains, x, torch, align(caps, gains, x[:RATE * 4], torch))


def refine(path, steps, di=(), seconds=90.0, seed=0, log=print, **kw):
    """(the refined Lite's .nam dict, ESR before, ESR after) for the capture at path (layers=P: a light
    one, see distil)."""
    cap = Capture(json.load(open(path)), os.path.splitext(os.path.basename(path))[0])
    return distil([cap], [1.0], steps, di, seconds, seed, log, **kw)


def batch_esr(p, t):
    """The error over the whole batch at once, as the held-out check measures it: an ESR per segment
    weighs a quiet tail as much as a hard chord and, on a Lite already close, trains away from the
    check (on TS808, 900 steps: 2.44% -> 2.35% per segment, 2.44% -> 2.09% this way)."""
    return ((p - t) ** 2).mean() / (t ** 2).mean()


def distil(caps, levels, steps, di=(), seconds=90.0, seed=0, log=print, lr=None, pre_emph=0.0,
           segment=SEGMENT, name=None, stop=None, progress=None, chain=False, layers=None):
    """(an A2 Lite .nam dict, ESR before, ESR after) trained to sound like the rig: the blend of caps at
    levels, or with chain=True the caps in series (levels then are the trims in dB before each stage).
    One capture is a refine of its own Lite. A blend starts from the loudest capture's Lite, a chain
    from its last stage's (the amp), from scratch when that has none. stop: a threading.Event that ends
    training early (the best so far is kept); progress(step, steps, esr, best) at each check.
    layers=P (1..23, default all): a light capture, only the first P layers trained (from the Lite's
    first P), written as a full A2 Lite with the later layers zero; ESR before is then the full Lite's."""
    import torch
    from nam.models import init_from_nam
    from nam.models._from_nam import _init_wavenet
    from nam.models.losses import apply_pre_emphasis_filter, esr

    n = len(nam_pack.KERNEL)
    layers = n if layers is None else int(layers)
    if not 1 <= layers <= n:
        raise ValueError(f"layers {layers}: 1..{n}")
    torch.manual_seed(seed)
    warm = len(caps) - 1 if chain else max(zip(levels, range(len(caps))))[1]
    lite = caps[warm].lite
    for c in caps:
        if c.warning:
            log(c.warning)
    if layers == n:
        student = init_from_nam(lite) if lite else _init_wavenet(lite_config(), RATE)
    else:
        student = _init_wavenet(prefix_config(lite["config"] if lite else lite_config(), layers), RATE)
        if lite:             # the Lite's first P layers, its rechannel and head
            src = init_from_nam(lite)
            student.load_state_dict({k: v for k, v in src.state_dict().items() if k in student.state_dict()})
            student._net._head_scale = src._net._head_scale
    size = "A2 Lite" if layers == n else f"light A2 Lite ({layers} of {n} layers)"
    log(f"{'chain' if chain else 'teachers'}: {(' > ' if chain else ', ').join(c.name for c in caps)}; "
        f"student: {size} {'from ' + caps[warm].name + chr(39) + 's Lite' if lite else 'from scratch'}")
    x, xv = signals(seconds, seed, di)
    t0 = time.time()
    if chain:
        g = chain_gains(caps, levels)
        y, yv = chain_target(caps, g, x, torch), chain_target(caps, g, xv, torch)
        note = "; stage gains " + ", ".join(f"{20 * math.log10(v):+.1f} dB" for v in g)
    else:
        gains = mix_gains(caps, levels)
        lags = align(caps, gains, xv[:RATE * 4], torch)
        y, yv = target(caps, gains, x, torch, lags), target(caps, gains, xv, torch, lags)
        note = f"; aligned by {lags} samples" if any(lags) else ""
    log(f"teachers run on {len(x) / RATE:.0f} s + {len(xv) / RATE:.0f} s held out in {time.time() - t0:.0f} s"
        + note)

    def val():
        student.eval()
        e = esr(run(student, xv, torch), yv).item()
        student.train()
        return e

    rf = student.receptive_field
    xt = torch.as_tensor(x)
    best_e = start = before = val() if lite else math.inf
    best = copy.deepcopy(student.state_dict())
    if lite and layers < n:      # a light one is held against the full Lite it stands in for
        before = esr(run(init_from_nam(lite).eval(), xv, torch), yv).item()
        log(f"the full Lite: held-out ESR {before:.5f}; its first {layers} layers alone: {start:.5f}")
    if progress and lite:
        progress(0, steps, start, start)
    near = start < 0.1          # a Lite already close (a refine) is nudged; one far off (a chain, a weld) is retrained
    if lite and not near:
        log(f"the starting Lite is {100 * start:.0f}% off the rig: trained as from scratch, kept only if better")
    opt = torch.optim.Adam(student.parameters(), lr=lr or (5e-5 if near else 3e-3))
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    student.train()
    every = max(50, steps // 20)
    t0 = time.time()
    for step in range(1, steps + 1):
        if stop is not None and stop.is_set():
            log(f"stopped at step {step - 1}: keeping the best so far")
            break
        starts = np.random.default_rng(seed * 1_000_003 + step).integers(rf - 1, len(x) - segment, BATCH)
        xb = torch.stack([xt[s - rf + 1: s + segment] for s in starts])
        yb = torch.stack([y[s: s + segment] for s in starts])
        p = student(xb, pad_start=False)
        loss = batch_esr(p, yb)
        if pre_emph:
            loss = loss + pre_emph * batch_esr(apply_pre_emphasis_filter(p, PRE_EMPH),
                                               apply_pre_emphasis_filter(yb, PRE_EMPH))
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if step % every == 0 or step == steps:
            e = val()
            if e < best_e:
                best_e, best = e, copy.deepcopy(student.state_dict())
            log(f"step {step}/{steps}: held-out ESR {e:.5f} (best {best_e:.5f}), {time.time() - t0:.0f} s")
            if progress:
                progress(step, steps, e, best_e)
    student.load_state_dict(best)
    student.eval()
    out = copy.deepcopy(lite) if lite else {"version": caps[warm].teacher_dict.get("version", "0.5.4"),
                                            "architecture": "WaveNet", "config": lite_config(), "sample_rate": RATE}
    if layers < n:
        student = padded(student, init_from_nam(lite).eval() if lite else _init_wavenet(lite_config(), RATE).eval())
    out["weights"] = [float(w) for w in student._export_weights()]
    out["sample_rate"] = RATE
    meta = dict(caps[0].d.get("metadata") or {}) if len(caps) == 1 else {}
    meta.update(out.get("metadata") or {} if len(caps) == 1 else {})
    if chain and len(caps) > 1:
        if caps[0].dbu is not None:
            meta["input_level_dbu"] = caps[0].dbu - levels[0]    # a +t dB first trim: an interface t dB hotter
        if caps[-1].out_dbu is not None:
            meta["output_level_dbu"] = caps[-1].out_dbu
        meta["nam_chain"] = [{"name": c.name, "trim_db": t} for c, t in zip(caps, levels)]
    elif len(caps) > 1:
        ref = next((c.dbu for c in caps if c.dbu is not None), None)
        if ref is not None:
            meta["input_level_dbu"] = ref
        meta["nam_weld"] = [{"name": c.name, "level": lv} for c, lv in zip(caps, levels)]
    if layers < n:
        meta["nam_light"] = {"layers": layers, "of": n}
        if not name:
            meta["name"] = f"{meta.get('name') or caps[0].name} [{layers} layers]"
    if name:
        meta["name"] = name
    meta["loudness"] = student._metadata_loudness() + (caps[0].loud_offset if len(caps) == 1 else 0.0)
    meta["nam_refine"] = {"teacher_weights": [len(c.teacher_dict["weights"]) for c in caps], "steps": steps,
                          "seed": seed, "held_out_esr_before": None if before == math.inf else before,
                          "held_out_esr_after": best_e}
    out["metadata"] = meta
    why = nam_pack.a2_mismatch(out["config"], 3)
    assert why is None and len(out["weights"]) == 1871, why
    return out, before, best_e


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_const", dest="steps", const=STEPS["quick"])
    g.add_argument("--deep", action="store_const", dest="steps", const=STEPS["deep"])
    g.add_argument("--steps", type=int)
    ap.add_argument("--di", action="append", default=[], help="a 48 kHz DI recording (repeatable)")
    ap.add_argument("--seconds", type=float, default=90.0, help="synthetic guitar to train on")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--layers", type=int, default=len(nam_pack.KERNEL),
                    help="train a light capture: only the first N of the 23 layers (23, 20, 16, 14)")
    a = ap.parse_args()
    if not 1 <= a.layers <= len(nam_pack.KERNEL):
        ap.error(f"--layers: 1..{len(nam_pack.KERNEL)}")
    steps = a.steps or STEPS["standard"]
    light = a.layers < len(nam_pack.KERNEL)
    out_path = a.output or os.path.splitext(a.input)[0] + (f" [{a.layers} layers].nam" if light else " HD Lite.nam")
    nam, before, after = refine(a.input, steps, a.di, a.seconds, a.seed, layers=a.layers)
    with open(out_path, "w") as f:
        json.dump(nam, f)
    was = "" if before == math.inf else f"{100 * before:.2f}% (the full Lite) -> " if light else f"{100 * before:.2f}% -> "
    print(f"[+] {out_path}: error against the teacher {was}{100 * after:.2f}% (held-out ESR), "
          f"loudness {nam['metadata']['loudness']:.1f} dB")


if __name__ == "__main__":
    main()
