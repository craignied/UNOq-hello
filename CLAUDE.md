# CLAUDE.md — Arduino UNO Q (this board)

## What this machine actually is

This is **not** a classic AVR/microcontroller Arduino. It is an **Arduino UNO Q**, a
hybrid board with two compute domains on one PCB:

- **MPU (Linux side):** Qualcomm **Dragonwing QRB2210**, quad-core ARM Cortex-A53
  (`aarch64`), running **Debian 13 (trixie)**. This is what you get a shell on. The
  board reports `Arduino UnoQ` in `/proc/device-tree/model`; hostname is `babyQ`.
- **MCU (real-time side):** an **STM32U585** (Cortex-M33) that runs an Arduino sketch.
  Its Arduino core is **Zephyr-based**, not AVR — sketches can `#include <zephyr/kernel.h>`
  and use `K_MUTEX_DEFINE`, etc. (`arduino:zephyr` platform).

The two halves talk over the **Router Bridge**. You write an "Arduino App" that has a
Python program (runs on Linux) and, optionally, a sketch (runs on the MCU); they RPC to
each other across the Bridge.

## The "special Python"

The board ships an Arduino Python SDK used inside apps. You will **not** find it in the
host `pip`/dist-packages — apps run in **Docker** containers (Docker is installed and
active), and the SDK lives in those images. Key imports:

- `from arduino.app_utils import App, Bridge, Frame, FrameDesigner, Logger`
  - `App.run()` / `App.run(user_loop=fn)` — app entrypoint / main loop.
  - `Bridge.call(name, *args)` — synchronous RPC to a sketch provider.
  - `Bridge.notify(name, *args)` — fire-and-forget RPC (used to stream frames).
  - `Frame` / `FrameDesigner` — helpers for LED-matrix pixel frames (see below).
  - `Logger("name")` — structured logging.
- `from arduino.app_bricks.<brick> import ...` — reusable "Bricks" (e.g. `web_ui.WebUI`,
  `dbstorage_sqlstore`, plus many Edge-AI bricks). `WebUI` serves on **port 7000** by
  default and can `expose_api('GET'|'POST', path, handler)`.

On the sketch side the matching header is `#include <Arduino_RouterBridge.h>`, with
`Bridge.begin()`, `Bridge.provide("name", fn)` to register callable providers.

## App layout (the unit you build and run)

```
<app>/
  app.yaml            # name, icon, description, list of `bricks:` used
  python/main.py      # runs on the Linux (MPU) side; entrypoint is App.run(...)
  sketch/sketch.ino   # runs on the MCU (optional; omit for Python-only apps)
  sketch/sketch.yaml  # profiles -> platform: arduino:zephyr
```

Minimal pattern (from the `blink` example):

```python
# python/main.py
from arduino.app_utils import *
import time
def loop():
    time.sleep(1)
    Bridge.call("set_led_state", True)
App.run(user_loop=loop)
```
```cpp
// sketch/sketch.ino
#include "Arduino_RouterBridge.h"
void setup() { pinMode(LED_BUILTIN, OUTPUT); Bridge.begin(); Bridge.provide("set_led_state", set_led_state); }
void loop() {}
void set_led_state(bool on) { digitalWrite(LED_BUILTIN, on ? LOW : HIGH); } // LOW = ON
```

## Onboard LED matrix

Driven on the **MCU** via `#include <Arduino_LED_Matrix.h>` (`Arduino_LED_Matrix matrix;`),
and controlled from Python by shipping pixel frames over the Bridge. Details taken from
the canonical `led-matrix-painter` example:

- Grid is **8 rows** high; the painter app uses a **13×8** pixel grid (`height=8, width=13`).
- Grayscale: sketch calls `matrix.setGrayscaleBits(3)` → per-pixel brightness **0..7**
  (8 levels). `BRIGHTNESS_LEVELS = 8` on the Python side.
- **Live draw:** Python sends a flat, row-major byte buffer (one byte per pixel, values
  0..7) via `Bridge.call("draw", frame_bytes)`; the sketch provider does `matrix.draw(frame.data())`.
- **Animations:** each frame is packed as **4× uint32 (128 bits, 1 bit/pixel on/off) +
  duration_ms**. Python streams frames with `Bridge.notify("load_frame", [w0,w1,w2,w3,ms])`
  then `Bridge.call("play_animation")`; the sketch buffers up to `MAX_FRAMES = 300` and
  plays them on a timer. Note the sketch reverses the bit order of each word before display.
- `Frame` / `FrameDesigner` (in `arduino.app_utils`) build/transform frames;
  `Frame.to_board_bytes()` produces the row-major byte buffer for `draw`.

**For scrolling "HELLO WORLD":** render text into a wide pixel bitmap in Python, then either
(a) stream horizontal slices as animation frames via `load_frame`/`play_animation`, or
(b) push each shifted 13×8 window with `Bridge.call("draw", ...)` on a timer in `user_loop`.
Study `/var/lib/arduino-app-cli/examples/led-matrix-painter/` (`sketch/sketch.ino` +
`python/main.py`) as the reference implementation.

## Running / building apps

- **`arduino-app-cli`** manages apps but **must run as user `arduino` (UID 1000)** — it
  refuses to run as any other user (including `craign`). Use `su - arduino` (needs the
  arduino user's password) or the App Lab GUI. Apps live in `/home/arduino/ArduinoApps/`.
- **App Lab** (`app-lab`) is a desktop GUI (Wails); it needs a graphical session (fails
  with "failed to init GTK" over a plain SSH shell). Also reachable as a web UI.
- **`arduino-cli`** (v1.5.1) builds/uploads sketches; the MCU core is `arduino:zephyr`
  (installed under `/home/arduino/.arduino15/packages/arduino/hardware/zephyr/`).
- Web UIs from the `web_ui` brick are served at `http://<board-ip>:7000`.

## Environment gotchas

- The current shell user is **`craign`** (uid 1002), *not* `arduino`. `sudo` here requires
  a password (no passwordless sudo). `/home/arduino/**` and
  `/home/arduino/.arduino15/**` are **not readable** to `craign`.
- Canonical, readable references (no permissions needed):
  - Examples: **`/var/lib/arduino-app-cli/examples/`** — see `blink`, `color-your-leds`,
    and **`led-matrix-painter`**.
  - Python API docs: **`/var/lib/arduino-app-cli/assets/<ver>/api-docs/arduino/`**
    (`app_bricks/*`, `app_peripherals/*`).
  - Brick catalog: `/var/lib/arduino-app-cli/assets/<ver>/bricks-list.yaml`.
- Board tooling on PATH: `arduino-app-cli`, `arduino-cli`, `app-lab`, `arduino-router`,
  `arduino-router-cli`, `arduino-linux-config`.
- The onboard RGB LEDs are split across domains: LEDs #1/#2 on the Qualcomm MPU, LEDs
  #3/#4 on the STM32 MCU (see `color-your-leds`). udev rule:
  `/etc/udev/rules.d/30-builtin-leds.rules`.

## This repo

Working dir `/home/craign/hello` — currently just holds this file. Goal: an app that
scrolls **"HELLO WORLD"** across the onboard LED matrix (see the LED-matrix section above).
