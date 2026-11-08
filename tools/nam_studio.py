#!/usr/bin/env python3
"""nam_studio.py - NAM Studio: weld up to three captures into one A2 Lite, refine a capture's Lite
against its own Full model, and convert .nam files to User IR .wav files for the HX Stomp and Helix
NAM A2 Lite firmware. A page in your browser on a server on this computer only (127.0.0.1); nothing
is uploaded anywhere. Training runs here, with torch (tools/nam_refine.py).

usage: nam_studio.py [--port 8765] [--no-browser]
Needs torch and neural-amp-modeler (README: NAM Studio).
"""
import argparse
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sharc"))
sys.path.insert(0, HERE)
import nam2ir  # noqa: E402
import nam_lite  # noqa: E402
import nam_pack  # noqa: E402
import nam_refine as nr  # noqa: E402

PAGE = os.path.join(os.path.dirname(HERE), "web", "studio.html")
STEPS = {"quick": 800, "standard": 3000, "deep": 10000}
CAPS, DIS, JOBS = {}, {}, {}
LOCK = threading.Lock()
_DEMO = {}


def demo_di():
    """The built-in test guitar: 8 s of the synthetic player, the same every time."""
    if "x" not in _DEMO:
        _DEMO["x"] = nr.synth_guitar(8.0, np.random.default_rng(7))
    return _DEMO["x"]


def wav16(y):
    """48 kHz mono 16-bit .wav bytes, brought to -18 dB RMS (peaks kept under full scale) so every
    source plays at about the same level."""
    y = np.asarray(y, np.float64)
    rms = np.sqrt(np.mean(y * y)) or 1.0
    y = y * (10 ** (-18 / 20) / rms)
    y = y / max(1.0, np.max(np.abs(y)) / 0.98)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(nr.RATE)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return b.getvalue()


def ir_wav(nam_dict):
    """The User IR .wav (tools/nam2ir.py) of a .nam dict, or raises ValueError with the reason."""
    with tempfile.TemporaryDirectory() as t:
        src, dst = os.path.join(t, "in.nam"), os.path.join(t, "out.wav")
        with open(src, "w") as f:
            json.dump(nam_dict, f)
        try:
            w, c = nam_pack.load(src, channels=nam_lite.C)
        except SystemExit as e:
            raise ValueError(str(e).replace(src, "this file"))
        bad = nam2ir.problems(src)
        if bad:
            raise ValueError("not an A2 Lite the kernel can run: " + "; ".join(bad))
        nam2ir.write_wav(dst, nam_lite.ir_samples(w, nam_pack.input_level_dbu(src), nam_pack.loudness(src)))
        return open(dst, "rb").read()


class Job:
    def __init__(self, caps, levels, steps, name, di, chain):
        self.id, self.caps, self.levels, self.steps, self.name = uuid.uuid4().hex[:8], caps, levels, steps, name
        self.chain = chain
        self.state, self.step, self.history, self.log, self.before, self.best = "running", 0, [], [], None, None
        self.result, self.error, self.stop, self.started = None, None, threading.Event(), time.time()
        self.di = di
        self.model = None

    def run(self):
        import torch
        from nam.models import init_from_nam
        try:
            def progress(step, steps, e, best):
                if step == 0:
                    self.before = e
                self.step, self.best = step, best
                self.history.append([step, e])
            out, before, after = nr.distil(self.caps, self.levels, self.steps, di=self.di, name=self.name,
                                           log=self.log.append, stop=self.stop, progress=progress,
                                           chain=self.chain)
            self.before, self.best, self.result = (None if before == float("inf") else before), after, out
            self.model = init_from_nam(out).eval()
            self.state = "done"
        except Exception as e:  # noqa: BLE001 (shown on the page)
            self.error, self.state = f"{type(e).__name__}: {e}", "failed"
        finally:
            torch.set_num_threads(torch.get_num_threads())

    def info(self):
        return {"id": self.id, "state": self.state, "step": self.step, "steps": self.steps, "history": self.history,
                "before": self.before, "best": self.best, "log": self.log[-12:], "error": self.error,
                "name": self.name, "elapsed": time.time() - self.started}


def safe_name(s, default="capture"):
    s = re.sub(r'\s+', " ", re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", s or "")).strip()
    return (s or default)[:80]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json", name=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if name:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self.send(200, open(PAGE, "rb").read(), "text/html; charset=utf-8")
        m = re.fullmatch(r"/api/job/(\w+)(?:/(nam|wav))?", self.path)
        if m and m.group(1) in JOBS:
            j = JOBS[m.group(1)]
            if not m.group(2):
                return self.send(200, j.info())
            if j.result is None:
                return self.send(409, {"error": "not finished"})
            base = safe_name(j.name, "weld")
            if m.group(2) == "nam":
                return self.send(200, json.dumps(j.result).encode(), "application/octet-stream", base + ".nam")
            return self.send(200, ir_wav(j.result), "audio/wav", base + ".wav")
        self.send(404, {"error": "not found"})

    def do_POST(self):
        try:
            return self.route()
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except SystemExit as e:
            self.send(400, {"error": str(e)})

    def route(self):
        p = self.path
        fname = safe_name(unquote(self.headers.get("X-Filename", "")), "capture.nam")
        if p == "/api/capture":
            d = json.loads(self.body())
            cap = nr.Capture(d, os.path.splitext(fname)[0])
            cid = uuid.uuid4().hex[:8]
            CAPS[cid] = cap
            return self.send(200, {"id": cid, "name": cap.name, "kind": cap.kind(), "dbu": cap.dbu,
                                   "loudness": cap.loudness, "has_lite": cap.lite is not None})
        if p == "/api/di":
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
                t.write(self.body())
            try:
                x = nr.read_wav(t.name)
            finally:
                os.remove(t.name)
            did = uuid.uuid4().hex[:8]
            DIS[did] = x
            return self.send(200, {"id": did, "seconds": len(x) / nr.RATE})
        if p == "/api/convert":
            d = json.loads(self.body())
            try:
                return self.send(200, ir_wav(d), "audio/wav", os.path.splitext(fname)[0] + ".wav")
            except ValueError as e:
                has_big = bool(d.get("weights")) or d.get("architecture") == "SlimmableContainer"
                return self.send(400, {"error": str(e), "distill": has_big})
        req = json.loads(self.body() or b"{}")
        if p == "/api/hear":
            return self.hear(req)
        if p == "/api/job":
            with LOCK:
                if any(j.state == "running" for j in JOBS.values()):
                    raise ValueError("a weld is already running: stop it first")
                caps, levels, chain = rig(req)
                di = []
                if req.get("di") in DIS:
                    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    t.close()
                    write_float_wav(t.name, DIS[req["di"]])
                    di = [t.name]
                default = caps[0].name + (" HD Lite" if len(caps) == 1 else " chain" if chain else " weld")
                j = Job(caps, levels, STEPS.get(req.get("quality"), STEPS["standard"]),
                        safe_name(req.get("name"), default), di, chain)
                JOBS[j.id] = j
            threading.Thread(target=j.run, daemon=True).start()
            return self.send(200, {"id": j.id})
        m = re.fullmatch(r"/api/job/(\w+)/stop", p)
        if m and m.group(1) in JOBS:
            JOBS[m.group(1)].stop.set()
            return self.send(200, {"ok": True})
        self.send(404, {"error": "not found"})

    def hear(self, req):
        import torch
        x = DIS[req["di"]][: nr.RATE * 20] if req.get("di") in DIS else demo_di()
        src = req.get("source")
        if src == "dry":
            return self.send(200, wav16(x), "audio/wav")
        if src == "result":
            j = JOBS.get(req.get("job"))
            if not j or j.model is None:
                raise ValueError("no result yet")
            return self.send(200, wav16(nr.run(j.model, x, torch).numpy()), "audio/wav")
        caps, params, chain = rig(req)
        return self.send(200, wav16(nr.rig_output(caps, params, x, torch, chain).numpy()), "audio/wav")


def rig(req):
    """(captures, levels or trims, chain?) of a request: mode "mix" (levels 0..1, not all 0) or
    "chain" (trims in dB before each stage, in signal order)."""
    caps = [CAPS[i] for i in req.get("ids") or [] if i in CAPS]
    if not caps:
        raise ValueError("load a capture first")
    chain = req.get("mode") == "chain" and len(caps) > 1
    if chain:
        params = [max(-24.0, min(24.0, float(v))) for v in req.get("trims") or [0.0] * len(caps)]
    else:
        params = [max(0.0, float(v)) for v in req.get("levels") or [1.0] * len(caps)]
        if sum(params) <= 0:
            raise ValueError("every level is at 0")
    return caps, params, chain


def write_float_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(nr.RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"NAM Studio: {url} (Ctrl+C to quit)")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
