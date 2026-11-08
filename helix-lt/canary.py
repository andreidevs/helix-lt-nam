#!/usr/bin/env python3
"""A first install for the Helix LT: stock 3.80.0 with one visible, harmless change.

The browser item of Xenomorph Fuzz (Mono) reads NAME instead: data in Entry 0, no code. Entry 1 (the
app's second copy) stays stock, as in the NAM build. It checks, at the least risk, that Line 6 Updater
takes a rebuilt LT image and the unit boots it (the changed name in Distortion shows it is running),
and gives a reason to rehearse the way back to stock.

usage: canary.py <stock Helix_LT_v3.80.0_0x7d01f5efb.hxf> [-o out.hxf]
"""
import argparse
import hashlib
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import hxf  # noqa: E402
import l6ia  # noqa: E402

LT_MD5 = "7505704bd858864e38147e776b3cb7b2"
BLIST_PTR_TAB, BLIST_CNT_TAB, BLIST_SLOTS = 0x2813ABB8, 0x2813ACE8, 76   # the LT's (HELIX_LT_FIRST_LOOK.md)
XENO_MONO_NI, XENO_TEXT = 1515, b"Xenomorph Fuzz"
NAME = b"Xeno LT TEST"


def pack(payload, donor):
    """The LT .hxf around an L6IA payload: the donor's HEAD and one dinf, sizes and MD5 updated; the
    last chunk unpadded, as Line 6's own LT file."""
    chunks = hxf._chunks(donor)
    head = bytearray([b for c, p, s, b in chunks if c == b"HEAD"][0])
    dinfs = [bytearray(b) for c, p, s, b in chunks if c == b"dinf"]
    assert len(dinfs) == 1, "not the LT's one-dinf layout"
    struct.pack_into(">I", head, 16, len(payload))
    head[20:36] = hashlib.md5(payload).digest()
    struct.pack_into(">I", dinfs[0], 12, len(payload))
    body = bytearray(b"L6FF")
    parts = [(b"HEAD", bytes(head)), (b"dinf", bytes(dinfs[0])), (b"data", zlib.compress(payload, 9))]
    for k, (cid, data) in enumerate(parts):
        body += cid + struct.pack(">I", len(data)) + data
        if len(data) & 1 and k < len(parts) - 1:
            body += b"\0"
    return b"FORM" + struct.pack(">I", len(body)) + bytes(body)


def rename(e0):
    """Entry 0 (byte-swapped to little-endian, as l6ia gives it) with the item renamed, and how many items."""
    e0 = bytearray(e0)
    n, segs, off = struct.unpack_from("<I", e0, 16)[0], [], 0x34
    for _ in range(n):
        sl, dst, nxt = struct.unpack_from("<3I", e0, off)
        segs.append((off + 12, sl, dst))
        off = nxt

    def fo(va, ln=4):
        return next(p + va - d for p, sl, d in segs if d <= va and va + ln <= d + sl)

    hits = 0
    for i in range(BLIST_SLOTS):
        lp, lc = (struct.unpack_from("<I", e0, fo(t + 4 * i))[0] for t in (BLIST_PTR_TAB, BLIST_CNT_TAB))
        for k in range(lc if lp else 0):
            item = fo(lp + 48 * k, 48)
            if struct.unpack_from("<I", e0, item + 4)[0] == XENO_MONO_NI:
                assert e0[item + 14: item + 40].rstrip(b"\0") == XENO_TEXT, e0[item + 14: item + 40]
                e0[item + 14: item + 40] = NAME.ljust(26, b"\0")
                hits += 1
    assert hits, "Xenomorph Fuzz (Mono) is in no browser list: not the stock LT 3.80.0 app"
    return l6ia.fix_internal_crcs(bytes(e0)), hits


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stock")
    ap.add_argument("-o", "--output", default=os.path.join(HERE, "build", "Helix_LT_v3.80.0_CANARY.hxf"))
    a = ap.parse_args()
    raw = open(a.stock, "rb").read()
    if hashlib.md5(raw).hexdigest() != LT_MD5:
        sys.exit(f"{a.stock}: not the stock Helix LT 3.80.0 file (MD5 {LT_MD5})")
    payload = zlib.decompress([b for c, p, s, b in hxf._chunks(raw) if c == b"data"][0])
    assert pack(payload, raw) == raw, "the stock LT .hxf does not round-trip byte for byte"
    e = l6ia.parse(payload)
    e0 = l6ia.swap32(payload[e[0]["payload_off"]: e[0]["payload_off"] + e[0]["payload_len"]])
    new0, hits = rename(e0)
    out, _, _ = l6ia.rebuild_archive(payload, {0: new0})
    ne = l6ia.parse(out)
    for i in range(1, len(ne)):
        assert out[ne[i]["payload_off"]: ne[i]["payload_off"] + ne[i]["payload_len"]] == \
            payload[e[i]["payload_off"]: e[i]["payload_off"] + e[i]["payload_len"]], f"Entry {i} changed"
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    img = pack(out, raw)
    open(a.output, "wb").write(img)
    print(f"[+] {a.output}: Xenomorph Fuzz (Mono) reads {NAME.decode()} in {hits} browser list(s); "
          f"only Entry 0 changed; MD5 {hashlib.md5(img).hexdigest()}")


if __name__ == "__main__":
    main()
