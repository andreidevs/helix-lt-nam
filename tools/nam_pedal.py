#!/usr/bin/env python3
"""nam_pedal.py - a NAM pedal capture as a pedal model for the Helix LT's NAM Pedal block (lt_port.py --pedal).

The NAM Pedal block costs about a third of a NAM block's DSP. It does not run the capture's WaveNet but a
fixed cheap structure fitted to it, in about 20 s on a laptop CPU:

    y = FIR d (curve 3 (FIR c (curve 2 (FIR b (curve 1 (FIR a (x)))))))

FIR a, b, c, d: 64, 64, 48, 256 taps, causal (y[n] = sum c[k] x[n-k]); curves: 65 knots evenly on [-4, 4],
linear between, the end segments continued beyond. The fit runs against the file's biggest model (the
teacher) on 30 s of synthetic guitar and white-noise bursts: an input gain search, 400 Adam steps on FIRs
a, b, c and the curves with FIR d solved in closed form on every batch (it is linear in the output, so
least squares gives it exactly, and the gradient flows through that solve), then an exact least-squares
FIR d on the whole signal. The loss is spectrally weighted (ESR + 0.5 pre-emphasis ESR + 0.5 x the mean
octave-band ESR, 40 Hz..20 kHz), so the lows and highs are matched, not only the loud mids. On a Benson
preamp at three gains: 0.4-1.7% held-out ESR, every octave band within 2 dB of the capture.

The fit adds NAM's standard reamp file (v3 input.wav, 48 kHz: its 17..180 s of guitar and bass DI) when it is
present as nam_v3_input.wav in %LOCALAPPDATA%/HX Edit NAM or next to this tool, or NAM_PEDAL_DI / --di give a
file: real playing fits high-gain pedals much better than the synthetic guitar (about 10 s more).

The .wav is a User IR (2,048 samples, 48 kHz float), as tools/nam2ir.py writes for a NAM capture: a
header (0.5, -0.5, 3.0, the scale 2^e, 627 / 1024 - a pedal model's word count, so a NAM block and older
kernels refuse it -, the input level word, 0, 0), then the 627 coefficients / 2^e in the order a, curve 1,
b, curve 2, c, curve 3, d. The loudness is normalised to nam_lite.LOUD_TARGET in FIR d.
Works best for pedals; a capture with an amp and a cabinet loses more (use a NAM block for those).

usage: nam_pedal.py capture.nam [-o out.wav] [--check sample.wav] [-v]
Needs torch, scipy and neural-amp-modeler (helix-lt-nam's .venv).
"""
import argparse
import json
import os
import sys
import time
import types

T_START = time.time()
sys.modules.setdefault("nam.train", types.ModuleType("nam.train"))   # skip lightning: ~6 s of imports
import numpy as np  # noqa: E402
import torch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "sharc"))
import nam_refine as nr  # noqa: E402
import nam_lite  # noqa: E402
import nam_pack  # noqa: E402
from nam2ir import write_wav  # noqa: E402

torch.set_num_threads(min(8, os.cpu_count() or 1))
torch.set_flush_denormal(True)
RATE = 48000
ORDER = ("a", "k1", "b", "k2", "c", "k3", "d")
TAPS = {"a": 64, "b": 64, "c": 48, "d": 256}
KNOTS, R = 65, 4.0
N_WORDS = sum(TAPS.values()) + 3 * KNOTS          # 627: the kernel's PED_N
BANDS = [(40, 100), (100, 200), (200, 400), (400, 800), (800, 1600), (1600, 3200), (3200, 6400), (6400, 12800),
         (12800, 20000)]
SECONDS, STEPS, LR, SEG, BATCH, WARM = 30.0, 400, 1e-2, 4096, 16, 512
W_PRE, W_BANDS = 0.5, 0.5
GAINS = (1, 2, 4, 8, 16, 32)


# ------------------------------------------------------------------ the model (torch, for the fit)
def fir(x, w):
    """Causal FIR along the last axis (w[0] = newest tap), by FFT."""
    t = x.shape[-1]
    n = 1 << (t + w.numel() - 1).bit_length()
    return torch.fft.irfft(torch.fft.rfft(x, n) * torch.fft.rfft(w, n), n)[..., :t]


def pwl(x, y):
    """65 knots on [-4, 4]; the index clamp makes the end segments continue linearly beyond +-4 (the
    kernel's TRUNC and clamp give the same index: u < 0 truncates to 0 as floor and clamp do)."""
    u = (x + R) * ((KNOTS - 1) / (2 * R))
    i = u.detach().floor().clamp(0, KNOTS - 2)
    f = u - i
    i = i.long()
    return y[:-1][i] + f * (y[1:] - y[:-1])[i]


def front(p, x):
    """Everything up to curve 3's output (FIR d is linear on it)."""
    for w, k in zip(p["firs"], p["curves"]):
        x = pwl(fir(x, w), k)
    return x


def chunked(f, x, chunk=1 << 18, ov=1024):
    out = []
    with torch.no_grad():
        for s in range(0, len(x), chunk):
            a = max(0, s - ov)
            out.append(f(x[None, a:s + chunk])[0, s - a:])
    return torch.cat(out)


# ------------------------------------------------------------------ the loss: a spectral weight
def pre_gain(f):
    return np.abs(1 - 0.85 * np.exp(-2j * np.pi * f / RATE)) ** 2


def weight_fn(y):
    """W(f) such that sum |E(f)|^2 W(f) = ESR + W_PRE pre-emphasis ESR + W_BANDS mean octave-band ESR
    (energies from the teacher's output over the whole fit signal)."""
    import scipy.signal as ss
    f, p = ss.welch(y, RATE, nperseg=4096)
    d0, dp = p.sum(), (p * pre_gain(f)).sum()
    db = [max(p[(f >= a) & (f < b)].sum(), 1e-12 * d0) for a, b in BANDS]
    cache = {}

    def w(n):                          # on the rfft grid of length n
        if n not in cache:
            fr = np.fft.rfftfreq(n, 1 / RATE)
            v = 1 / d0 + W_PRE * pre_gain(fr) / dp
            for (a, b), e in zip(BANDS, db):
                v = v + W_BANDS / len(BANDS) * ((fr >= a) & (fr < b)) / e
            cache[n] = torch.tensor(v / v.max(), dtype=torch.float32)
        return cache[n]
    return w


def wloss(p, t, w):
    e, y = torch.fft.rfft(p - t), torch.fft.rfft(t)
    wn = w(p.shape[-1])
    return ((e.real ** 2 + e.imag ** 2) * wn).sum() / ((y.real ** 2 + y.imag ** 2) * wn).sum()


def solve_d(z, y, w, n=TAPS["d"], ridge=1e-6):
    """The FIR d minimizing the weighted error of fir(z, d) against y: Toeplitz normal equations from
    weighted auto/cross spectra (differentiable)."""
    t = z.shape[-1]
    L = 1 << (2 * t).bit_length()
    wn = w(L)
    zf, yf = torch.fft.rfft(z, L), torch.fft.rfft(y, L)
    rzz = torch.fft.irfft(((zf.real ** 2 + zf.imag ** 2) * wn).reshape(-1, wn.numel()).sum(0), L)[:n]
    ryz = torch.fft.irfft((yf * zf.conj() * wn).reshape(-1, wn.numel()).sum(0), L)[:n]
    a = rzz[(torch.arange(n)[:, None] - torch.arange(n)[None]).abs()]
    return torch.linalg.solve(a + ridge * rzz[0] * torch.eye(n), ryz)


# ------------------------------------------------------------------ the fit
def default_di():
    """Real playing to add to the fit: NAM_PEDAL_DI, else NAM's standard reamp file (v3 input.wav, its
    guitar and bass DI parts) as nam_v3_input.wav in %LOCALAPPDATA%\\HX Edit NAM or next to this tool."""
    names = [os.environ.get("NAM_PEDAL_DI", "")]
    names += [os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "HX Edit NAM", "nam_v3_input.wav"),
              os.path.join(HERE, "nam_v3_input.wav")]
    return [n for n in names if n and os.path.isfile(n)][:1]


def read_di(path):
    """A DI file's samples for the fit (48 kHz). NAM's v3 reamp file (190 s): its 17..180 s, the playing
    (Benson G8 6.7% -> 4.2%, Kilt fuzz 22% -> 5.8%, SD-1 6.7% -> 4.5% on a guitar sample; KOT Dist 9.5% -> 10%)."""
    x = nr.read_wav(path)
    if abs(len(x) - 190 * RATE) < RATE:
        x = x[17 * RATE: 180 * RATE]
    return x.astype(np.float32)


DI = []                                         # the DI files convert() adds (main: --di, or default_di())


def fit_signal(seconds=SECONDS, seed=3):
    """Synthetic guitar plus white noise bursts (0.003..0.3: guitar alone leaves > 10 kHz unconstrained),
    then any DI files (real playing: the synthetic guitar is duller and thinner in the lows)."""
    rng = np.random.default_rng(seed)
    parts = [nr.synth_guitar(seconds, rng)]
    for lv in np.geomspace(0.003, 0.3, 8):
        parts += [(rng.standard_normal(RATE // 4) * lv).astype(np.float32), np.zeros(2400, np.float32)]
    parts += [read_di(p) for p in DI]
    return np.concatenate(parts)


def init(gain):
    firs = []
    for name in "abc":
        v = torch.zeros(TAPS[name])
        v[0] = gain if name == "a" else 1.0
        firs.append(v.requires_grad_())
    curves = [torch.tanh(torch.linspace(-R, R, KNOTS)).requires_grad_() for _ in range(3)]
    return {"firs": firs, "curves": curves, "d": torch.zeros(TAPS["d"])}


def fit(xt, yt, steps=STEPS, log=lambda s: None, progress=None):
    torch.manual_seed(0)
    rng = np.random.default_rng(0)
    w = weight_fn(yt.numpy())

    def batch(b):
        idx = rng.integers(0, len(xt) - SEG, b)
        return torch.stack([xt[i:i + SEG] for i in idx]), torch.stack([yt[i:i + SEG] for i in idx])

    xb, yb = batch(2 * BATCH)
    best = None
    with torch.no_grad():                       # input gain: tanh curves, d by least squares
        for g in GAINS:
            p = init(g)
            z = front(p, xb)[:, WARM:]
            e = float(wloss(fir(z, solve_d(z, yb[:, WARM:], w)), yb[:, WARM:], w))
            log(f"  gain {g}: {e:.4f}")
            if best is None or e < best[0]:
                best = (e, g)
    p = init(best[1])
    params = p["firs"] + p["curves"]
    opt = torch.optim.Adam(params, lr=LR)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, LR, total_steps=steps, pct_start=0.2)
    for st in range(steps):
        xb, yb = batch(BATCH)
        z, t = front(p, xb)[:, WARM:], yb[:, WARM:]
        loss = wloss(fir(z, solve_d(z, t, w)), t, w)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        sched.step()
        if st % 50 == 49:
            log(f"step {st + 1}/{steps}: weighted error {loss.item():.5f}")
            if progress:
                progress(st + 1, steps)
    with torch.no_grad():                       # final d: exact least squares on the whole signal
        z = chunked(lambda v: front(p, v), xt)
        p["d"] = solve_d(z[None, WARM:], yt[None, WARM:], w)
    return p


EQ_MATCH = True                                 # match the teacher's spectrum after the fit (eq_match)
EQ_BOOST, EQ_CUT = 6.0, 3.0                     # at most +6 dB / -3 dB


def eq_match(d, z, y, log=lambda s: None):
    """FIR d with the model's long-term spectrum brought to the teacher's: least squares lowers a band's gain
    where the model's output there is only partly like the teacher's (that lowers the error), which cuts
    highs and lows. The 1/3-octave level ratio (teacher / model) on z -> y, limited to +EQ_BOOST / -EQ_CUT
    dB, as a minimum-phase filter folded into d (its first TAPS['d'] taps, the last 32 tapered)."""
    from scipy.signal import welch
    n = TAPS["d"]
    model = np.convolve(z, d)[:len(z)]
    f, pm = welch(model, RATE, nperseg=8192)
    _, pt = welch(y, RATE, nperseg=8192)
    lf = np.log2(np.maximum(f, 1.0))
    db = 10 * np.log10((pt + 1e-20) / (pm + 1e-20))
    sm = np.array([db[np.abs(lf - c) <= 1 / 6].mean() for c in lf])             # 1/3 octave
    lo, hi = np.searchsorted(f, 40.0), np.searchsorted(f, 20000.0)
    sm[:lo], sm[hi:] = sm[lo], sm[hi - 1]
    g = np.clip(sm, -EQ_CUT, EQ_BOOST)
    N = 8192
    mag = np.interp(np.fft.rfftfreq(N, 1 / RATE), f, g)
    c = np.fft.irfft(np.log(10 ** (mag / 20)), N)                                # real cepstrum
    c[1:N // 2] *= 2
    c[N // 2 + 1:] = 0
    h = np.fft.irfft(np.exp(np.fft.rfft(c, N)), N)                               # minimum phase
    out = np.convolve(d, h)[:n]
    out[-32:] *= np.hanning(64)[32:]
    log("eq match (dB, 40 Hz .. 16 kHz octaves): " + " ".join(
        f"{np.interp(fc, f, g):+.1f}" for fc in (40, 80, 160, 315, 630, 1250, 2500, 5000, 10000, 16000)))
    return out


def load_teacher(d):
    from nam.models import init_from_nam
    teacher, _ = nr.models(d)
    return init_from_nam(nr.upgrade(teacher)).eval()


def convert(d, teacher=None, log=lambda s: None, progress=None):
    """dict(a, k1, b, k2, c, k3, d) of plain floats for the capture in d (a .nam dict), the loudness
    normalised in d as a NAM block would."""
    teacher = teacher or load_teacher(d)
    x = fit_signal()
    y = nr.run(teacher, x, torch).float()
    p = fit(torch.as_tensor(x), y, log=log, progress=progress)
    dd = p["d"].detach().numpy().astype(np.float64)
    if EQ_MATCH:                                # on the real playing (the DI files at the end) if any
        k0 = len(x) - sum(len(read_di(q)) for q in DI) if DI else 0
        z = chunked(lambda v: front(p, v), torch.as_tensor(x[k0:])).numpy().astype(np.float64)
        dd = eq_match(dd, z, y.numpy()[k0:].astype(np.float64), log)
    f, k = [v.detach() for v in p["firs"]], [v.detach() for v in p["curves"]]
    m = {n: [float(v) for v in t] for n, t in zip(ORDER, (f[0], k[0], f[1], k[1], f[2], k[2], dd))}
    loud = nr.nam_pack_number((d.get("metadata") or {}).get("loudness"))
    if loud is not None:
        g = 10.0 ** ((nam_lite.LOUD_TARGET - loud) / 20.0)
        m["d"] = [v * g for v in m["d"]]
    return m


def ir_words(m, dbu=None):
    """The User IR's 2,048 words for the pedal model m."""
    coefs = [v for n in ORDER for v in m[n]]
    assert len(coefs) == N_WORDS
    e = 0
    while max(abs(v) for v in coefs) / 2.0 ** e > 15.5:
        e += 1
    vals = [0.5, -0.5, 3.0, 2.0 ** e, N_WORDS / 1024.0, nam_lite.level_word(dbu), 0.0, 0.0]
    vals += [v / 2.0 ** e for v in coefs]
    assert max(abs(v) for v in vals) < nam_lite.IR_LIMIT, "a sample HX Edit would refuse"
    return [nam_pack.f2b(v) for v in vals] + [0] * (nam_lite.IR_SAMPLES - len(vals))


# ------------------------------------------------------------------ the kernel's arithmetic, for --check
def play(m, x):
    """The pedal model as the DSP kernel runs it (numpy, float64)."""
    knots = np.linspace(-R, R, KNOTS)

    def curve(v, ky):
        ky = np.asarray(ky)
        i = np.clip(np.floor((v + R) * (KNOTS - 1) / (2 * R)), 0, KNOTS - 2).astype(int)
        f = (v - knots[i]) * (KNOTS - 1) / (2 * R)
        return ky[i] + f * (ky[i + 1] - ky[i])

    v = np.asarray(x, np.float64)
    for fw, kn in (("a", "k1"), ("b", "k2"), ("c", "k3")):
        v = curve(np.convolve(v, m[fw])[:len(v)], m[kn])
    return np.convolve(v, m["d"])[:len(v)]


def read_sample(path):
    import wave
    from scipy.signal import resample_poly
    with wave.open(path, "rb") as f:
        ch, sw, rate, raw = f.getnchannels(), f.getsampwidth(), f.getframerate(), f.readframes(f.getnframes())
    if sw != 2:
        raise SystemExit(f"{path}: 16-bit WAV only")
    x = np.frombuffer(raw, "<i2").reshape(-1, ch).mean(1) / 32768.0
    if rate != RATE:
        g = np.gcd(rate, RATE)
        x = resample_poly(x, RATE // g, rate // g)
    return (x * 0.5 / np.max(np.abs(x))).astype(np.float32)


def report(m, d, teacher, sample=None):
    """Held-out ESR and pre-emphasis ESR (synthetic guitar, another seed), and with a sample its
    octave-band levels against the capture (dB), all on the pedal model before loudness."""
    loud = nr.nam_pack_number((d.get("metadata") or {}).get("loudness"))
    g = 10.0 ** ((nam_lite.LOUD_TARGET - loud) / 20.0) if loud is not None else 1.0
    raw = dict(m, d=[v / g for v in m["d"]])
    xh = nr.synth_guitar(10.0, np.random.default_rng(11))
    yh = nr.run(teacher, xh, torch).numpy().astype(np.float64)
    ph = play(raw, xh)
    s = slice(2048, None)
    pre = lambda v: v[1:] - 0.85 * v[:-1]  # noqa: E731
    esr = lambda p, t: float(np.sum((p - t) ** 2) / np.sum(t ** 2))  # noqa: E731
    out = f"held-out ESR {100 * esr(ph[s], yh[s]):.2f}%, pre-emphasis ESR {100 * esr(pre(ph[s]), pre(yh[s])):.2f}%"
    if sample:
        xs = read_sample(sample)
        ref = nr.run(teacher, xs, torch).numpy().astype(np.float64)

        def spec(v):
            f = np.fft.rfftfreq(len(v), 1 / RATE)
            pw = np.abs(np.fft.rfft(v)) ** 2
            return np.array([10 * np.log10(pw[(f >= a) & (f < b)].sum() + 1e-20) for a, b in BANDS])
        b = spec(play(raw, xs)) - spec(ref)
        out += "\nbands (dB against the capture): " + "  ".join(f"{lo}-{hi}: {v:+.1f}" for (lo, hi), v in zip(BANDS, b))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("nam")
    ap.add_argument("-o", "--output", help='default: "<name> PEDAL.wav" next to the capture')
    ap.add_argument("--check", metavar="SAMPLE", nargs="?", const="", help="report the error (and bands on a sample)")
    ap.add_argument("--json", help="also write the coefficients as JSON")
    ap.add_argument("--di", action="append", default=None,
                    help="a 48 kHz DI recording to add to the fit (repeatable); default: NAM's v3 reamp file if "
                         "present (see default_di), --di none for synthetic guitar only")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    DI[:] = default_di() if a.di is None else [p for p in a.di if p.lower() != "none"]
    if a.verbose:
        print("fit signal: synthetic guitar, noise bursts" + "".join(f", {os.path.basename(p)}" for p in DI))
    d = json.load(open(a.nam, encoding="utf-8"))
    out = a.output or os.path.splitext(a.nam)[0] + " PEDAL.wav"
    teacher = load_teacher(d)
    m = convert(d, teacher, print if a.verbose else (lambda s: None))
    dbu = nr.nam_pack_number((d.get("metadata") or {}).get("input_level_dbu"))
    write_wav(out, ir_words(m, dbu))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(m, f)
    print(f"wrote {out} in {time.time() - T_START:.0f} s: a pedal model (627 words) for the NAM Pedal block; "
          f"HX Edit: import into a User IR slot, then set NAM Pedal's Model knob to that slot")
    if a.check is not None:
        print(report(m, d, teacher, a.check or None))


if __name__ == "__main__":
    main()
