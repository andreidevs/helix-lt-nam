# NAM A2 Lite on the Helix LT (v3.80.0): first look

2026-11-07. Static only, no LT run yet. Input: `Helix_LT_v3.80.0_0x7d01f5efb.hxf`
(file MD5 `7505704bd858864e38147e776b3cb7b2`, payload MD5 `f449ef308e61ee82ef48cf63d4052d7b`).
Compared with what [HELIX_FLOOR_FEASIBILITY.md](HELIX_FLOOR_FEASIBILITY.md) and the Floor port
([savedadodo/helix-floor-nam-lite @ c7cd0bac](https://github.com/savedadodo/helix-floor-nam-lite/tree/c7cd0bacaf7e08c0de2b5fedfccb05d13826e9f0/helix-floor),
which ran on a Floor, see [Suddl3's recall test](https://github.com/Suddl3/hx-stomp-nam-lite/blob/floor-a2-lite-recall-test/docs/research/HELIX_FLOOR_RECALL.md))
record about the Floor, and with the stock `Helix_Floor_v3.80.0_0x7d01f5efb.hxf`
(MD5 `805caa03e8a30fd6ff7892f32ed5a9f4`, the file the Floor port builds from).

## Floor against LT, entry by entry

| Entry | What | Floor | LT | |
|---|---|---|---|---|
| 0, 1 | main app, its copy | 0x171cc0 | 0x178008 | relinked (below) |
| 2 | SHARC LDR | 0x7bdc0, 186 blocks | 0x7bd98, 188 blocks | relinked: same 384-word header, 16 blocks identical, the rest the same code with addresses a few words apart |
| 3 | "4321" image | 0x7444 | 0x2fec | different |
| 4 | model descriptors | 863 | 863 | **only models 0 and 1 differ**: `HD2_AppDSP0/1` on the Floor, `HelixLT_AppDSP0/1` on the LT |
| 5 | graph library | 0xc25434 | 0xc24b48 | **only blobs 1 and 2 differ** (those two models: each DSP's path graph); Blob 0 and every other model's graph identical |
| 6..10, 15 | | | | identical |
| 11, 12, 13, 14 | | | | differ (not touched by the port) |

So every model, composite and primitive graph is the Floor's; what differs is each DSP's path graph
(the one the Floor port's `stage_slots2.py` changes), the M4 app and the SHARC program, all three
the same code relinked.

## Container

- One dinf (kind 0, offset 0, the whole L6IA), no trailer: the Floor's layout. `hxf.py unpack`,
  `l6ia.py`, `l6ia_verify.py` (ALL OK) and `l6ia.rebuild_archive` (no-op identical) work unchanged.
- **The data chunk is odd (0x2d1cbaf) and Line 6's file has no pad byte after it** (FORM size
  0x2d1cc0f). `hxf.py pack` and the Floor port's `floor_hxf.py` both add one, so a round trip is
  1 byte longer than stock (the zlib stream itself is identical). An LT pack must leave the final
  pad out.
- 16 entries, as the Floor: 0 main app (type 2), 1 its copy (type 3, same bytes), 2 SHARC LDR,
  3 "4321" image (12 KB; the Floor's is 29 KB), 4 model descriptors, 5 graph library, 6/7 a second
  small descriptor/blob pair (23 models, 4 blobs).

## Main application (Entry 0)

- 4 segments: 0x10000000 (0x112a8; the Floor's 0x11870), 0x10088a10, 0x28000000 (0x15d630, the
  code), 0x20000000. Zero-initialised memory starts at the code's end (0x2815d630 is referenced),
  so nothing can be appended there; the Floor port puts its cave at the end of seg0 instead
  (0x10011870 on the Floor, 0x100112a8 here, upper bound 0x10020000 unchecked on the LT).
- Static model table: 0x2813bba4, 823 rows (as the Stomp and Floor), max preset ID 832, 32 free.
  Xenomorph Fuzz Mono: name index 1515, preset ID 555.
- **The table code is the Floor's shifted by +0x6998**: all five base pointers, the end pointer,
  the count (`movw #823`) and the three count-1 loads (`movw #822`) sit at the Floor port's
  `stage_main.py` addresses + 0x6998, and so does the budget check (Floor 0x28135070, LT 0x2813ba08,
  `movw r0, #9000`).
- Other regions shift differently: Table 2 (823 x 44 B at 0x280e0828) has its base pointer at
  0x280e0824 and count at 0x280e0784, the Floor's + 0x5a8. The browser lists and subcategory
  tables do not sit at Floor + 0x6998; not located yet.

## SHARC program (Entry 2)

- 0x7bd98 bytes (the Floor's 0x7bdc0): **17,000 bytes left** in the 512 KiB partition. 188 LDR blocks.
- Primitive table at 0x200000: 290 records, as the Floor. **0x9c75 is not there.** 23 of the
  Stomp's other unused IDs are registered; of those, by every composite in Blob 0 and every model
  blob's node tree, 0x2aa8/0x2aaa/0x2aab/0x261a are referenced on the LT and 0x0128, 0x012e, 0x0100,
  0x0838, 0x2392, 0x238f, 0x000e, 0x0205, 0x045e, 0x0207, 0x2ab6, 0x021f, 0x012c, 0x012d, 0x0130,
  0x0087, 0x020d, 0x0105, 0x0104 and 0x0209 are not. (The 87 small IDs from 0x200650 up are
  unreferenced too, but look like system primitives; not candidates.)
- 0x822's record (the hook template) is at 0x2004b0, with the same relative offsets as the Stomp's.

## Model database and graphs (Entries 4, 5)

863 models (Floor 863), 863 blobs, Blob 0 0x7a612 words with 457 composites.
HD2_AmpLine6Clarity id 804, Xenomorph Fuzz Mono id 168 (10 parameters), Stereo 464.

## The Floor port's addresses on the LT

Every Floor address in the Floor port's build (`build_floor2.py` at c7cd0bac) has an LT twin,
found by matching bytes around it in the two stock images, then checked against the code there
(capstone, instruction for instruction, branch targets and pc literals aside). The table is in
[helix-lt/lt_port.py](../../helix-lt/lt_port.py).

- Main app: Table 1's code +0x6998 (pointers, count, count-1 loads), Table 2 +0x5a8, the
  browser lists and folder tables +0x6998 (42 lists identical, 4 in categories 17/18 differ: the
  Floor's extra I/O; Amp, where NAM goes, is the same), the budget check and its two callers
  +0x6998 / +0x6b44, the move check's two callers +0x6b48, the block counter +0x6b44 (109
  instructions the same, its DSP struct offsets 0xac4/0xaf0/0x8164 included), the title sites:
  A 0x280abf9e (its `beq.w` differs, so its stock bytes do), B 0x280ad230, the IR path 0x280ac35c,
  the IR Single name branch 0x280ac7bc. The partition table is the Floor's, word for word.
- The cave after seg0: the LT's seg0 ends at 0x100112a8. A few u32 values between there and
  0x100113b4 occur in the app, all inside byte tables at 0x2801xxxx, not in literal pools: taken
  as data. Only the unit can confirm the cave is free.
- DSP program: heap a 0x96b9a..0x9ba55 (Floor 0x96ba4..0x9ba5f), heap b 0xe4458..0xe673c
  (0xe4466..0xe674a), the free top of Block 3 from 0xe728c (0xe729a), same sizes; Blob 0
  (0x21cd06, 0x7a612 words), Heap 6, Heap 7, the User IR store (0x2af982) and heap c are the
  Floor's. Primitive 0x128's record (the hook) names its PM handler at 0x8cf32 (Floor 0x8cf39).

## What this means

The LT is the Floor's firmware relinked, not a new design. The way in is the Floor port
(DSP layout, streamed weights, two NAM per DSP, the M4 guards) with the addresses above:
[helix-lt/](../../helix-lt/README.md). The Floor port's own build, run here from the stock Floor
file, gives `95d9e096cbf4f334d8cf7cd0b94e3eb8`, the image that ran on a Floor.

From the Floor's run: one NAM block costs ~37% of a DSP in a plain path, more in a split path
(keep NAM out of split paths), and the declared cost there (2700) is too low. Install: Line 6
Updater in Offline Mode. Floor recovery: footswitches 6 + 12 at power-on (update mode), then the
stock file. On the LT, try that recovery on the stock firmware before installing any build.
