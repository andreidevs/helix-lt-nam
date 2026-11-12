# Changelog

Major changes, newest first. The repository has no version numbers, so each entry is dated and names its commit. Status labels follow the README: "ran on" means a person ran that build on that unit.

## 2026-11-12

- **Helix LT: four NAM blocks** ([README](README.md#four-nam-blocks-and-lighter-captures), [technical guide](helix-lt/README.md)). `helix-lt/lt_port.py --layers` builds `Helix_LT_v3.80.0_NAM4_LAYERS.hxf` (MD5 225a88d9): NAM A2 Lite, NAM Lite 20, NAM Lite 16 and NAM Lite 14, at 3,650, 3,300, 2,950 and 2,770 of a DSP's 9,000. The kernel skips the layers a light capture leaves empty, and each block plays silence for a capture with more layers than it allows. It ran on a Helix LT, together with HX Edit NAM v0.5.0, which knows the new blocks. The 23-layer cost was measured on the LT: 36.2% of a DSP, 0.4% more than the one-block build.
- **Lighter captures.** `tools/nam_refine.py --layers P` trains a capture's A2 Lite down to its first P layers against its own bigger model. The converter (`tools/nam2ir.py` and the web page) writes P into the `.wav`, and the setup page shows which block it needs. A light capture plays the same on any build; only `--layers` builds save DSP with it.

## 2026-11-08

- **Helix LT** (`c9b90bc`, [helix-lt/](helix-lt/README.md)). `helix-lt/lt_port.py` builds savedadodo's Helix Floor port with the LT's addresses. The build 8330973f ran on a Helix LT: it boots, Amp → NAM → NAM A2 Lite is in the menu, a capture plays. The first build (ecb8d773) showed a blue screen at boot: on the LT one of the IR-title patch sites is not 4-aligned, so the jump there read a wrong address; it now goes through a `bl` and a relay. The canary and the two bring-up images also ran on that LT. Two NAM blocks per path and the real DSP load aren't confirmed on an LT yet.
- **NAM Studio** (`bac7d24`, [README](README.md#nam-studio)). `tools/nam_studio.py`, a page on 127.0.0.1: blend up to three captures into one A2 Lite, chain pedals and an amp, refine a TONE3000 A2 file's Lite against its own Full, convert `.nam` files to User IR `.wav` files. Converting needs only numpy; training needs torch and neural-amp-modeler.

## 2026-11-06

- **Loudness normalisation.** The converter (`tools/nam2ir.py` and the web page) stores a capture's loudness in the `.wav`, and the amp brings its output to −18 dB, as the NAM plugin's Normalized mode does. `.wav` files from older converters play as before. A capture converted again plays at a new volume. The converter also refuses captures not trained at 48 kHz and models that aren't the A2 shape. Builds: HX Stomp a37659d0 (ran on an HX Stomp from RAM; test suite 48 pass, 0 fail, 1 skip), HX Stomp XL 8918ab60 (not run on an XL), HX Effects 2efb9879 (not run on an HX Effects).
- **HX Effects: the capture's name in overview mode** (`26271c2`, PR #9 by Jerry Chuang). The scribble strip shows "Model: name" while Model turns, and the strips and parameter view show Model as a slot number (1..128). This build (MD5 4d2a4a8a) ran on an HX Effects.
- **README and setup page name all three units** (HX Stomp, HX Stomp XL, HX Effects), with a table of what differs between them.

## 2026-11-05

- **On-unit QA tools** (`eecdc60`, [QA.md](QA.md)). `tools/hx_smoke.py` runs a build from RAM and tests it over USB: NAM blocks, knobs, presets, the DSP budget, a stock block of each category, and the recorded audio. It also adds the USB control (`hx_ctl.py`), a one-step RAM run (`hx_ramrun.sh`), a reamp tool and the factory-preset sweep. The suite from this repository ran on an HX Stomp against the Stomp build (MD5 e6431a5f): 48 pass, 0 fail, 1 skip.
- **Research notes** (`388ecc3`, [docs/research/](docs/research/README.md)). Measurements and studies from the work: DSP load, the two-amp limit, why HX Edit dropped NAM blocks, input calibration, the factory-preset sweep. They also cover NAM A2 Full and the Helix Floor, both stopped.
- **HX Effects: NAM under Distortion → Mono** (`675c333`, PR #6 by Jerry Chuang). NAM now sits in Xenomorph Fuzz Mono's own place in the list, and Mid Freq and Q make room for the capture's name. This build ran on an HX Effects. The scribble strips still show the Model number, not the name.

## 2026-11-04

- **Ten knobs and a tone stack** (`f88f347`). Bass, a sweepable Mid with Q, Treble and High Cut come after the model, each ±12 dB and flat at 5.0. The knobs are in live order, with Input, Treble and Output on page 1.
  - NAM moves to Xenomorph Fuzz Mono's preset ID (555), so HX Edit keeps the blocks. MM4 Frequency Shifter is back.
  - **Presets saved with an earlier build don't open NAM in this one:** re-add the block.
- **HX Effects support** (`f88f347`), under Distortion → NAM. There is no RAM run for the HX Effects.

## 2026-11-03

- **HX Edit keeps NAM blocks** (`e091746`). HX Edit rewrites a whole preset for some edits and leaves out any model it doesn't know. NAM therefore took MM4 Frequency Shifter's preset ID (461), with four knobs: Model, Polarity, Input and Output. It moved from 147/148 to 461, so older presets need the block re-added.
- **No tone bands, DSP cost 2220** (`90f5ab5`). The four-knob layout came to the HX Stomp XL too.

## 2026-10-31

- **23.1% of the DSP a block** (`0ebc830`, `b59c8a0`). The far layers' rings moved into the block's own DM and PM memory. DSP cost is now 2275, and three NAM blocks leave room for a stereo Simple Delay.

## 2026-10-30

- **Up to three NAM blocks** (`0f31004`, `362ad2e`). The third goes under Distortion → NAM (preset ID 148), so the two-amp limit doesn't stop it. The kernel dropped from 26.9% to 24% a block.

## 2026-10-29

- **Several NAM blocks, each with its own capture, and the IR name in the block title** (`d5e3010`). The Model knob picks the User IR slot.
- **Knob changes** (`aedc853`, `7f3c9a7`, `387954e`). A Polarity knob was added, and Drive is shown as Input. The built-in model is gone: captures come only from the User IR slots.

## 2026-10-28

- **Run a build from RAM** (`6b340c3`, [RAM_RUN.md](RAM_RUN.md)). You can try a build from the setup page (WebUSB) or from `tools/hxf_ram.py`, and nothing is written to the eMMC. It ran on an HX Stomp, and on an XL from the setup page.
- **Input level from the capture** (`4cd7f15`, `1b280ef`). The kernel trims the input by 11.5 dBu minus the capture's `input_level_dbu`.

## 2026-10-27

- **Setup page** (`4508be0`, `a4f30e3`). It builds the firmware in the browser and guides you through the whole setup, in 10 languages.
- **HX Stomp XL build** (`6e42562`).
- **Smooth model changes** (`358a04f`, `b2d0b6e`). Changing the model crossfades with no gap, and there's no pop when you change it in silence.
- **Tests and CI** (`ba8e0b7`): a pytest suite, run by GitHub Actions.

## 2026-10-26

- **First release** (`9703157`, `3a77d6f`). NAM A2 Lite is built into the stock HX Stomp 3.80.0 firmware, and a web converter turns a `.nam` capture into a User IR.
