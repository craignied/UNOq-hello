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
  refuses to run as any other user (including `craign`) or as root. The binary is a
  *statically linked* Go executable, so the `getuid()==1000` check can't be shimmed with
  `LD_PRELOAD` and there's no env override. Treat the **command** as single-seat.
- **App Lab** (`app-lab`) is a desktop GUI (Wails); it needs a graphical session (fails
  with "failed to init GTK" over a plain SSH shell). Also reachable as a web UI.
- **`arduino-cli`** (v1.5.1) builds/uploads sketches; the MCU core is `arduino:zephyr`
  (installed under `/home/arduino/.arduino15/packages/arduino/hardware/zephyr/`).
- Web UIs from the `web_ui` brick are served at `http://<board-ip>:7000`.

### The real interface is the daemon, not the CLI (works as any local user)

The CLI is just a thin client. All privileged work is done by **`arduino-app-cli daemon
--port 8800`** (systemd unit `arduino-app-cli.service`, running as `User=1000`/arduino,
with docker + access to `arduino-router` which owns the MCU serial link `/dev/ttyHS1`).
It listens on **`http://127.0.0.1:8800`** and its HTTP API is reachable by **any local
user** — the UID check lives only on the client, not the daemon. So you do **not** have to
*be* `arduino` to drive the board. Verified endpoints (as `craign`):

- `GET  /v1/version` → `{"version":"0.11.1"}`
- `GET  /v1/apps` → JSON list; each `id` is `base64("<namespace>:<name>")`, namespaces
  seen: `examples:`, `user:`, `local:`.
- `GET  /v1/apps/events` → SSE stream of app state (`event: app` + JSON per app).
- `POST /v1/apps/import?namespace=user&overwrite=true` with multipart form field
  **`file=@app.zip`** → imports an app (returns `{"id": "..."}`, HTTP 201). **This is how
  this repo's app got registered as `user:hello-app` — done entirely as `craign`.** After
  import it also shows up in App Lab.
- Lifecycle verbs `run`/`build`/`install`/`stop` are `GET /v1/apps/<verb>?id=<id>`
  (streaming). NOTE: the exact accepted form of the `id` param for these was not yet
  cracked — passing the stored base64 id returns `412 {"details":"invalid id"}`. TODO if
  you want fully headless run: capture what App Lab / the arduino-user CLI actually sends
  (e.g. tcpdump on loopback :8800, or strace the CLI as arduino).

**Easiest way to actually run this app today:** open **App Lab**, pick **"Hello World
Scroll"** (already imported), hit Run. CLI fallback: `su - arduino` then
`arduino-app-cli run ...`.

### Using your own user (`craign`) for board projects

Develop and version-control under `/home/craign` as normal, and register/deploy via the
daemon API above — no need to live in `/home/arduino`. To give `craign` the *actual*
hardware/runtime capability the `arduino` user has (independent of the cosmetic UID gate),
add it to the same groups:

```
sudo usermod -aG docker,dialout,gpiod,video,audio,render,input,netdev,bluetooth,adm craign
```

- `docker` → run/inspect the app containers directly (⚠ docker group ≈ root-equivalent).
- `dialout` → serial link to the MCU; `gpiod` → board GPIO lines.
- Re-login (or `newgrp`) after changing groups. `craign` currently has only `sudo,users`.

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

## Git / GitHub workflow

`gh` (GitHub CLI) is installed and authenticated for user `craignied` over **HTTPS**, and
is registered as git's credential helper. So git and `gh` commands work non-interactively
from a normal shell here (including from inside Claude Code) — **no** SSH keys and **no**
token pasting needed.

- Remote: `origin` → `https://github.com/craignied/UNOq-hello.git`. Default branch `main`.
- Push / pull just work: `git push`, `git pull`, `git push -u origin <branch>`.
- Use `gh` for GitHub-side operations, e.g. `gh repo view`, `gh pr create`,
  `gh repo create` (only if the remote repo doesn't exist yet — `git push` won't create it).
- Auth lives in `~/.config/gh/hosts.yml`; check it with `gh auth status`.

## This repo

Working dir `/home/craign/hello` — holds `CLAUDE.md` and `README.md`. Goal: an app that
scrolls **"HELLO WORLD"** across the onboard LED matrix (see the LED-matrix section above).
