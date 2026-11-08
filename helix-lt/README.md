# NAM A2 Lite on the Helix LT (experimental: runs on one LT)

The Helix LT's firmware 3.80.0 is the Helix Floor's relinked: the same models, composites and
DDR2 map, with its own path graphs, main application and DSP program
([HELIX_LT_FIRST_LOOK.md](../docs/research/HELIX_LT_FIRST_LOOK.md)). So this build is
**savedadodo's Floor port** ([helix-floor-nam-lite @ 29aea81](https://github.com/savedadodo/helix-floor-nam-lite/tree/29aea8169d93151b25db61bf1140969de9d7b916/helix-floor),
the build that ran on a Floor) with every Floor address replaced by the LT's. `lt_port.py`
holds the replacements, each one found by matching the stock Floor and LT images and checked
against the code it points at.

> **Status: this build (`8330973f`) runs on one LT: it boots, shows Amp > NAM > NAM A2 Lite and a
> capture plays** (2026-11-08); two NAM per path and the meter are not reported yet. On that LT: the canary, TEST1_SEG0 and
> TEST2C_MEMORY boot and play as stock; the first NAM build (`ecb8d773`) blue-screened at boot,
> while its DSP half alone (Entries 2, 4, 5 with Entry 0 stock, two images) booted. The cause,
> found in the image: title site A is 2 mod 4 on the LT, so the Floor's `ldr.w pc,[pc,#0]` there read
> its target 2 bytes early (`lt_port.py` docstring); this build goes through a `bl` and the relay.
>
> On the Floor, at this commit (one unit; the port's
> FINDINGS.md, and [Suddl3's recall test](https://github.com/Suddl3/hx-stomp-nam-lite/blob/floor-a2-lite-recall-test/docs/research/HELIX_FLOOR_RECALL.md)
> on an earlier build): a NAM block costs ~35% of a DSP (52.8K cycles a call; declared 3,600), two
> on one DSP play (20 minutes of checks, none bad), presets recall. **The UI freezes of earlier
> builds are fixed:** the kernel masked interrupt P9I for each call, believing it was external-port
> DMA channel 0's, but both units' stock DSP programs route P9I to link port 1 (the link between
> the two DSPs); the kernel now leaves interrupts alone (93 minutes of play, no freeze; the old
> kernel froze 3 times in 48). The LT's DSP program routes its interrupts the same way (the same
> PICR words as the Floor's).

## Build

Needs Python 3.10+ with `numpy` and `capstone`, a checkout of the Floor port at
`29aea8169d93151b25db61bf1140969de9d7b916`, and Line 6's stock `Helix_LT_v3.80.0_0x7d01f5efb.hxf`
(MD5 `7505704bd858864e38147e776b3cb7b2`).

```sh
git clone https://github.com/savedadodo/helix-floor-nam-lite floor-port
git -C floor-port checkout 29aea8169d93151b25db61bf1140969de9d7b916
python helix-lt/lt_port.py floor-port path/to/Helix_LT_v3.80.0_0x7d01f5efb.hxf
```

It copies the Floor port to `helix-lt/build/lt_port`, applies the LT's addresses (a replacement
that doesn't match exactly stops the build), checks that the stock LT file round-trips through the
pack, then runs the Floor port's own build there (its bit-exact KernelCheck in the simulator, the
partition sizes, the guard tests): about 5 minutes. The result is
`helix-lt/build/Helix_LT_v3.80.0_NAM2_PERSONAL.hxf` (MD5 `8330973f8b445050b826c093eb4c48b4`,
pinned in `tests/test_helix_lt.py`). **Never share it**: it is Line 6's firmware.

`--meter` builds the Floor port's cycle-meter test image instead (each NAM block plays its own
call's cycles, `floor/meter_read.py` reads them from a recording); `--diag` its beep-code image.

The LT build against the Floor's: the Floor port at this commit, built here from the stock Floor
file, gives `f4338695c5fa965f9100a0d82e632b7e`, its NOMASK_C3600 image, the one on the Floor now.
The LT build changes the same four entries, with the same steady KernelCheck count (34,874
instructions a call), preset ID (380) and DSP cost (3,600); Entry 2 has 5,384 bytes spare.

## First day with an LT, in this order

Each step needs the previous one to have worked. All images go in with Line 6 Updater, Offline Mode.

1. **Stock first.** Back up presets and IRs in HX Edit. Hold footswitches 6 + 12 while powering on: if
   update mode comes up, install the stock `Helix_LT_v3.80.0_0x7d01f5efb.hxf` from it. If it doesn't,
   stop here: no way back has been shown on an LT.
2. **The canary**, `python helix-lt/canary.py <stock LT .hxf>` (`build/Helix_LT_v3.80.0_CANARY.hxf`):
   stock with one browser item renamed, Distortion > Xenomorph Fuzz (Mono) reads **Xeno LT TEST**;
   only Entry 0 changes, 14 bytes. It boots and shows the name: the Updater takes our images and the
   unit runs them. Then go back to stock through update mode once, on purpose.
3. **The two bring-up images** (`lt_port.py ... --staged`), as the Floor port was brought up; each
   should behave exactly as stock:
   - `Helix_LT_v3.80.0_TEST1_SEG0.hxf`: stock, but the app's first segment grown by as many zero bytes
     as the NAM build grows it. Boots and runs normally: the bootloader takes the bigger segment and
     the memory the NAM build's guards and tables go into (from 0x100112a8) is free on the LT.
   - `Helix_LT_v3.80.0_TEST2C_MEMORY.hxf`: stock, but the DSP memory changes alone (each DSP's last big
     block slot made normal, heaps a and b shrunk to match). Boots, presets with two amps per path
     play on both paths. If one of these fails, the NAM build would fail the same way.
4. **NAM** (`Helix_LT_v3.80.0_NAM2_PERSONAL.hxf`): boots, Amp > NAM > NAM A2 Lite is there, a capture
   imported as a User IR plays with Model = its slot. Start with one NAM a path; two on one path
   play on the Floor at this commit (the 3,600 cost lets the unit refuse what won't fit).
5. **The meter** (`--meter`, `Helix_LT_v3.80.0_NAM2_METER.hxf`): the block plays numbers instead of
   audio (it is loud: monitors down). Record a few seconds of the LT's USB input 1 at 48 kHz exactly
   (pan the lane 100L if the capture endpoint is mono, as the Floor's is) and run the Floor port's
   `helix-floor/floor/meter_read.py take.wav --v4` (needs ffmpeg; in the build's work tree):
   the cycles a call, of 150,000 per block, corrected for the gain after the block. The Floor reads
   ~52.8K (35%).
6. **Only if NAM is silent or wrong**, the diag image (`--diag`, `Helix_LT_v3.80.0_NAM2_DIAG.hxf`):
   where the kernel would play silence it beeps N times, then pauses (~260 ms), for its first failure
   since boot. 1 DMA channel 0 busy; 4 a DMA failed loading the model; 5 no model (Model outside
   1..128, or that slot holds no NAM capture); 6 a channel 0 transfer timed out; 8 the instance's
   memory is not where the kernel expects (a split path); 9 the model ran but output 0.0; 10 no code.
   No beep and silence: the kernel is never called. Dry guitar: no slot or SDRAM block.

## Before installing

1. Back up presets and IRs in HX Edit.
2. **Rehearse the recovery on stock firmware first.** On the Floor: hold footswitches 6 + 12 while
   powering on (update mode), then Line 6 Updater, Offline Mode, the stock file. Nobody has tried
   that on an LT; if it doesn't give update mode on yours, don't install.
3. Install with Line 6 Updater, Offline Mode, choosing the built file.

Entry 1 (the main application's second copy) stays stock, as on the Floor.

## Use

As on the Floor port: Amp > NAM > NAM A2 Lite; captures converted with this repository's converter
(`tools/nam2ir.py` or the setup page) and imported as User IRs in HX Edit; Model = the IR slot.
HX Edit can drop NAM blocks when it rewrites a preset: edit NAM presets on the unit.
