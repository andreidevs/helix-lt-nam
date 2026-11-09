# NAM A2 Lite for Line 6 Helix LT

**helix-lt-nam** adds a Neural Amp Modeler (NAM) A2 Lite block to Line 6 Helix LT firmware 3.80.0. The block runs captures on the Helix LT's DSP. The project also includes **NAM Studio**, a local app for blending, chaining, refining and converting captures.

[Установка и восстановление на русском](helix-lt/INSTALL_RU.md) · [Helix LT technical guide](helix-lt/README.md) · [NAM Studio](#nam-studio)

## Helix LT

**Experimental.** On November 8, 2026, the build was tested on one Helix LT. The unit booted, listed **Amp → NAM → NAM A2 Lite**, and played a capture. Running two NAM blocks on the same path and measuring DSP usage on the LT still need hardware verification.

### Build

Use Python 3.10 or newer, Git and your own stock Helix LT 3.80.0 file, `Helix_LT_v3.80.0_0x7d01f5efb.hxf`. The build checks the stock file against MD5 `7505704bd858864e38147e776b3cb7b2`.

```sh
git clone https://github.com/andreidevs/helix-lt-nam
cd helix-lt-nam
python -m pip install numpy capstone
git clone https://github.com/savedadodo/helix-floor-nam-lite floor-port
git -C floor-port checkout 29aea8169d93151b25db61bf1140969de9d7b916
python helix-lt/lt_port.py floor-port "path/to/Helix_LT_v3.80.0_0x7d01f5efb.hxf"
```

The output is `helix-lt/build/Helix_LT_v3.80.0_NAM2_PERSONAL.hxf`. Its expected MD5 is `8330973f8b445050b826c093eb4c48b4`. Keep the generated firmware for personal use.

### Install and recover

Installing modified firmware is at your own risk.

1. Back up your presets and IRs in HX Edit, then close it.
2. Rehearse recovery with the stock file. Power off, hold footswitches **6 + 12** (MODE and TAP), and power on to enter update mode. Reinstall stock 3.80.0 in Line 6 Updater's **Offline Mode**. Proceed once that works.
3. Install the generated `Helix_LT_v3.80.0_NAM2_PERSONAL.hxf` using the same update procedure. To recover from a boot failure, repeat step 2 with the stock file.

For the optional test builds, cycle meter and diagnostic beep codes, see the [Helix LT technical guide](helix-lt/README.md). The [Russian guide](helix-lt/INSTALL_RU.md) covers the full build, install and recovery process.

### Load a capture

1. Convert a 48 kHz, 3-channel A2 Lite capture using NAM Studio's **Convert** tab or the command below. A multi-size `.nam` file with an A2 Lite model works too.

   ```sh
   python tools/nam2ir.py "My Amp.nam" -o "My Amp NAM.wav"
   ```

2. Import the resulting `.wav` into a **User IR** slot in HX Edit. On the LT, add **Amp → NAM → NAM A2 Lite** and set **Model** to that slot number. Start with one NAM block per path.

Edit NAM presets on the LT. HX Edit can drop NAM blocks when rewriting a preset because the LT build uses model ID 380. If a preset opens empty after switching firmware, leave it unsaved and return to the build it was saved with.

## NAM Studio

NAM Studio runs in your browser via a local server at `127.0.0.1`. It processes captures on your computer.

| Mode | What it does |
| --- | --- |
| **Blend** | Mix up to three captures in parallel into one A2 Lite model. |
| **Chain** | Train one A2 Lite model from a series of captures, such as pedals into an amp. |
| **Refine** | Train an A2 Lite model against a larger capture, including the Full model in a multi-size A2 file. |
| **Convert** | Batch-convert compatible `.nam` captures to User IR `.wav` files for HX Edit. |

Use the built-in guitar signal or your own 48 kHz DI for training and A/B playback. Export a trained model as `.nam` or as a User IR `.wav`.

From the repository root, create a virtual environment with `python -m venv .venv` and run the commands for your platform.

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install numpy torch neural-amp-modeler
.\.venv\Scripts\python.exe tools/nam_studio.py
```

```sh
# macOS and Linux
.venv/bin/python -m pip install numpy torch neural-amp-modeler
.venv/bin/python tools/nam_studio.py
```

The Convert tab needs only `numpy`. Training also uses `torch` and `neural-amp-modeler`.

## HX Stomp, HX Stomp XL and HX Effects

The fork also includes the upstream `build.py` workflow for these three devices on firmware 3.80.0. Follow the device-specific instructions in the [upstream README](https://github.com/nocaseguy/hx-stomp-nam-lite/blob/003bc0dc4d0dbb67b46f69e151cd1fbb3ae5e46c/README.md) or the [browser setup guide](https://nocaseguy.github.io/hx-stomp-nam-lite/web/).

On **HX Stomp**, `build.py --customos` adds optional CustomOS features such as tuner settings, a BPM display, a DSP meter and a custom boot screen. The combined NAM and CustomOS build still needs on-device testing. See the [firmware notes](FIRMWARE_NOTES.md) and [resource limits](docs/resource-limits.md).

## Credits and license

- Helix LT port based on [savedadodo's Helix Floor port](https://github.com/savedadodo/helix-floor-nam-lite).
- NAM kernel, SHARC tools and HX workflow from [Derek Bui's hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite).
- Capture format from [Steven Atkinson's Neural Amp Modeler](https://github.com/sdatkinson/neural-amp-modeler).
- Optional CustomOS features from [wisemandenny's hx-stomp-customOS](https://github.com/wisemandenny/hx-stomp-customOS).

The source is licensed under GPL-3.0-or-later. See [LICENSE](LICENSE), [NOTICE](NOTICE) and the [changelog](CHANGELOG.md).
