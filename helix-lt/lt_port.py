#!/usr/bin/env python3
"""NAM A2 Lite for the Helix LT 3.80.0: the Helix Floor port with the LT's addresses.

The LT's firmware is the Floor's relinked (docs/research/HELIX_LT_FIRST_LOOK.md): the same
models, composites and DDR2 map, its own path graphs, main app and DSP program. So the LT build
is savedadodo's Floor port (https://github.com/savedadodo/helix-floor-nam-lite, commit FLOOR_PORT,
the build that ran on a Floor, helix-floor/floor/build_floor2.py) with every Floor address
replaced by the LT's, each found by matching the stock Floor and LT images:

- Main app (Entry 0): table code +0x6998, Table 2 +0x5a8, the guards' callers +0x6b44..+0x6b48,
  the title sites -0x132..-0x1c6; each site's code compared instruction for instruction
  (branch targets aside), the block counter's DSP struct offsets included. seg0 ends at
  0x100112a8 (Floor 0x10011870): the cave starts there.
- DSP program (Entry 2): heap a (Block 0) 0xa words lower, heap b and the free top of Block 3
  0xe lower, same sizes; primitive 0x128's record names its PM code 7 words lower. Blob 0, Heap 6,
  Heap 7, the User IR store and heap c are where they are on the Floor.
- The .hxf: the LT's data chunk is odd and Line 6 doesn't pad it, so neither does the pack.

usage: lt_port.py <floor-port checkout at FLOOR_PORT> <stock Helix_LT_v3.80.0_0x7d01f5efb.hxf>
                  [-o out.hxf] [--work DIR]
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys

FLOOR_PORT = "c7cd0bacaf7e08c0de2b5fedfccb05d13826e9f0"
LT_MD5 = "7505704bd858864e38147e776b3cb7b2"
FLOOR_MD5 = "805caa03e8a30fd6ff7892f32ed5a9f4"
HERE = os.path.dirname(os.path.abspath(__file__))

# (file in helix-floor/floor, Floor text, LT text, how many times the Floor text occurs)
PATCHES = [
    ("build_floor.py", f'STOCK_MD5 = "{FLOOR_MD5}"', f'STOCK_MD5 = "{LT_MD5}"', 1),
    ("floor_hxf.py", f'FLOOR_MD5 = "{FLOOR_MD5}"', f'FLOOR_MD5 = "{LT_MD5}"', 1),
    ("floor_hxf.py", "        if len(data) & 1:\n", "        if len(data) & 1 and cid != b'data':\n", 1),
    ("stage_slots.py", "HEAP_A = (0x96BA4, 0x9BA5F, 0x4EBB)", "HEAP_A = (0x96B9A, 0x9BA55, 0x4EBB)", 1),
    ("stage_slots.py", "HEAP_B = (0xE4466, 0xE674A, 0x22E4)", "HEAP_B = (0xE4458, 0xE673C, 0x22E4)", 1),
    ("stage_slots2.py", "(0x9ba5f - (0x4ebb - dm), 0xe674a - (0x22e4 - pm))",
     "(0x9ba55 - (0x4ebb - dm), 0xe673c - (0x22e4 - pm))", 1),
    ("nam_floor.py", '"R3": (0x9ba5f - 0xeb8, 0x9ba5f)', '"R3": (0x9ba55 - 0xeb8, 0x9ba55)', 1),
    ("nam_floor.py", '"R1": (0xe729a, 0xe8000)', '"R1": (0xe728c, 0xe8000)', 1),
    ("nam_floor.py", '"R2": (0xe674a - 0x6d8, 0xe674a)', '"R2": (0xe673c - 0x6d8, 0xe673c)', 1),
    ("nam_floor.py", "HEAP_A, HEAP_B = (0x96BA4, 0x9BA5F - 0xEB8), (0xE4466, 0xE674A - 0x6D8)",
     "HEAP_A, HEAP_B = (0x96B9A, 0x9BA55 - 0xEB8), (0xE4458, 0xE673C - 0x6D8)", 1),
    ("nam_floor2.py", '"R3": (0x9b6b1, 0x9ba5f)', '"R3": (0x9b6a7, 0x9ba55)', 1),
    ("nam_floor2.py", '"R1": (0xe729a, 0xe8000)', '"R1": (0xe728c, 0xe8000)', 1),
    ("nam_floor2.py", '"R2": (0xe6624, 0xe674a)', '"R2": (0xe6616, 0xe673c)', 1),
    ("nam_floor2.py", "HEAP_A2, HEAP_B2 = (0x96BA4, 0x9b6b1), (0xE4466, 0xe6624)",
     "HEAP_A2, HEAP_B2 = (0x96B9A, 0x9b6a7), (0xE4458, 0xe6616)", 1),
    ("stage_kernel.py", "0x60C1F5, 0x8CF39,", "0x60C1F5, 0x8CF32,", 1),
    ("stage_main.py", "TAB1_BASE_PTRS = (0x28134D70, 0x28134DBC, 0x28134DD4, 0x28134EC8, 0x28134F80)",
     "TAB1_BASE_PTRS = (0x2813B708, 0x2813B754, 0x2813B76C, 0x2813B860, 0x2813B918)", 1),
    ("stage_main.py", "TAB1_END_PTR = 0x28134DB8", "TAB1_END_PTR = 0x2813B750", 1),
    ("stage_main.py", "TAB1_CNT_INSN = 0x28134DC0", "TAB1_CNT_INSN = 0x2813B758", 1),
    ("stage_main.py", "TAB1_CNT_M1_INSNS = (0x28134DA8, 0x28134E32, 0x28134EDA)",
     "TAB1_CNT_M1_INSNS = (0x2813B740, 0x2813B7CA, 0x2813B872)", 1),
    ("stage_main.py", "TAB2_BASE_PTR, TAB2_CNT_INSN = 0x280E027C, 0x280E01DC",
     "TAB2_BASE_PTR, TAB2_CNT_INSN = 0x280E0824, 0x280E0784", 1),
    ("stage_main.py", "BLIST_PTR_TAB, BLIST_CNT_TAB = 0x28134220, 0x28134350",
     "BLIST_PTR_TAB, BLIST_CNT_TAB = 0x2813ABB8, 0x2813ACE8", 1),
    ("stage_main.py", "SUBCAT_CNT, SUBCAT_NAMES = 0x28134480, 0x281344CC",
     "SUBCAT_CNT, SUBCAT_NAMES = 0x2813AE18, 0x2813AE64", 1),
    ("stage_main.py", "CAVE, CAVE_END = 0x10011870, 0x10020000", "CAVE, CAVE_END = 0x100112A8, 0x10020000", 1),
    ("stage_main.py", "SEG0 = (0x10000000, 0x11870)", "SEG0 = (0x10000000, 0x112A8)", 1),
    ("arm_guards.py", "CAVE = 0x10011870", "CAVE = 0x100112A8", 1),
    ("arm_guards.py", "TRAMP = 0x28135070", "TRAMP = 0x2813BA08", 1),
    ("arm_guards.py", "AVAIL_RET = 0x2814B7FF", "AVAIL_RET = 0x28152197", 1),
    ("arm_guards.py", "MOVE_RET = 0x2811DE75", "MOVE_RET = 0x281249B9", 1),
    ("arm_guards.py", "C1_RET, C2_RET = 0x28125ADF, 0x28125CF9", "C1_RET, C2_RET = 0x2812C627, 0x2812C841", 1),
    ("ir_title.py", 'SITE_A, SITE_A_STOCK = 0x280AC164, bytes.fromhex("337b0f2b00f00481")',
     'SITE_A, SITE_A_STOCK = 0x280ABF9E, bytes.fromhex("337b0f2b00f0db81")', 1),
    ("ir_title.py", 'SITE_B, SITE_B_STOCK = 0x280AD37C, bytes.fromhex("2b7b0f2b05d0")',
     'SITE_B, SITE_B_STOCK = 0x280AD230, bytes.fromhex("2b7b0f2b05d0")', 1),
    ("ir_title.py", "IR_PATH, NON_IR, IR_NAME = 0x280AC374, 0x280AC16C, 0x280AC8EE",
     "IR_PATH, NON_IR, IR_NAME = 0x280AC35C, 0x280ABFA6, 0x280AC7BC", 1),
    ("ir_title.py", "B_IR, B_RET = 0x280AD38E, 0x280AD382", "B_IR, B_RET = 0x280AD242, 0x280AD236", 1),
    ("ir_title.py", "RELAY = 0x28135078", "RELAY = 0x2813BA10", 1),
]


def make_tree(src, work):
    """A copy of the Floor port at `work` with PATCHES applied; each patch must match exactly."""
    floor = os.path.join(src, "helix-floor", "floor")
    if not os.path.isfile(os.path.join(floor, "build_floor2.py")):
        sys.exit(f"{src}: not a checkout of the Floor port (no helix-floor/floor/build_floor2.py)")
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(src, work, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
    texts = {}
    for name, old, new, n in PATCHES:
        path = os.path.join(work, "helix-floor", "floor", name)
        t = texts.get(path) or open(path, encoding="utf-8").read()
        if t.count(old) != n:
            sys.exit(f"{name}: {old!r} occurs {t.count(old)} times, expected {n}: "
                     f"is the checkout at {FLOOR_PORT}?")
        texts[path] = t.replace(old, new)
    for path, t in texts.items():
        open(path, "w", encoding="utf-8", newline="").write(t)
    print(f"[+] LT tree at {work}: {len(PATCHES)} patches in {len(texts)} files")


def roundtrip(work, stock):
    """The stock LT .hxf must come back byte for byte from its own payload (the pack's padding)."""
    sys.path.insert(0, os.path.join(work, "helix-floor", "floor"))
    sys.path.insert(0, os.path.join(work, "tools"))
    import zlib
    import floor_hxf
    import hxf
    raw = open(stock, "rb").read()
    payload = zlib.decompress([b for c, p, s, b in hxf._chunks(raw) if c == b"data"][0])
    assert floor_hxf.pack(payload, raw) == raw, "the stock LT .hxf does not round-trip byte for byte"
    print("[+] stock LT .hxf round-trips byte for byte")


def staged(work, stock, outdir):
    """The Floor port's two bring-up images on the LT, from this build: test1, stock but seg0 grown by
    as many zero bytes as the build grows it (the cave: does the bootloader take it, and is that
    memory free?); test2c, stock but the slots and heaps (Entries 2 and 5, the DSP memory) alone."""
    floor = os.path.join(work, "helix-floor", "floor")
    sys.path.insert(0, floor)
    import build_staged
    import l6ia
    import patch_amp as pa
    import stage_main
    raw = open(stock, "rb").read()
    data, _ = pa.load_l6ia_from_any(stock)
    full, _ = pa.load_l6ia_from_any(os.path.join(work, "helix-floor", "build", "floor2_s4.l6ia"))
    e0, f0 = pa.get_entry_swapped(data, 0), pa.get_entry_swapped(full, 0)
    n = stage_main.segments(f0)[0][2] - stage_main.segments(e0)[0][2]
    img, _, _ = l6ia.rebuild_archive(data, {0: build_staged.grow_seg0(e0, n)})
    assert pa.get_entry_swapped(img, 1) == e0
    build_staged.check_and_pack(img, "test1_seg0_only.hxf", raw)
    r = subprocess.run([sys.executable, os.path.join(floor, "build_test2c.py"), stock], cwd=work,
                       env={**os.environ, "PYTHONUTF8": "1"})
    if r.returncode:
        sys.exit("build_test2c.py failed")
    for src, dst in (("test1_seg0_only.hxf", "Helix_LT_v3.80.0_TEST1_SEG0.hxf"),
                     ("test2c_bigslot_heaps.hxf", "Helix_LT_v3.80.0_TEST2C_MEMORY.hxf")):
        shutil.copyfile(os.path.join(work, "helix-floor", "build", src), os.path.join(outdir, dst))
        print(f"[+] {dst}: MD5 {hashlib.md5(open(os.path.join(outdir, dst), 'rb').read()).hexdigest()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("floor_port")
    ap.add_argument("stock")
    ap.add_argument("-o", "--output", default=os.path.join(HERE, "build", "Helix_LT_v3.80.0_NAM2_PERSONAL.hxf"))
    ap.add_argument("--work", default=os.path.join(HERE, "build", "lt_port"))
    ap.add_argument("--meter", action="store_true", help="the Floor port's cycle-meter test image (nam_floor5m)")
    ap.add_argument("--diag", action="store_true", help="the Floor port's beep-code test image (nam_floor5d)")
    ap.add_argument("--staged", action="store_true", help="also the two bring-up images (see staged())")
    a = ap.parse_args()
    stock, out, work = (os.path.abspath(p) for p in (a.stock, a.output, a.work))
    if hashlib.md5(open(stock, "rb").read()).hexdigest() != LT_MD5:
        sys.exit(f"{stock}: not the stock Helix LT 3.80.0 file (MD5 {LT_MD5})")
    make_tree(os.path.abspath(a.floor_port), work)
    roundtrip(work, stock)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    flags = ["--meter"] * a.meter + ["--diag"] * a.diag
    r = subprocess.run([sys.executable, os.path.join(work, "helix-floor", "floor", "build_floor2.py"), stock, "-o", out,
                        *flags], cwd=work, env={**os.environ, "PYTHONUTF8": "1"})
    if r.returncode:
        sys.exit("build_floor2.py failed")
    out = out.replace("NAM2_PERSONAL", "NAM2_METER" if a.meter else "NAM2_DIAG") if flags else out
    if a.staged:
        staged(work, stock, os.path.dirname(out))
    print(f"\nHelix LT build: {out}\nMD5 {hashlib.md5(open(out, 'rb').read()).hexdigest()}. Personal build: never share it.")


if __name__ == "__main__":
    main()
