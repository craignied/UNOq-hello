# CLAUDE.md — Arduino UNO Q

Reference for building and running projects on this board. The workflow that works is:
**develop as `craign` in a git repo, deploy with `./run.sh` (the daemon HTTP API).**

## The board

Not a classic Arduino — a hybrid with two compute domains on one PCB:

- **MPU (Linux side):** Qualcomm Dragonwing **QRB2210**, quad-core ARM Cortex-A53
  (`aarch64`), running **Debian 13**. You get a shell here (`babyQ`); an app's Python runs
  here.
- **MCU (real-time side):** **STM32U585** (Cortex-M33) running a **Zephyr**-based Arduino
  sketch (`arduino:zephyr` platform). Drives the hardware (LED matrix, GPIO, …).

The two halves talk over the **Router Bridge**.

## What an "app" is

An app is a folder with a Linux half and (optionally) an MCU half:

```
app.yaml            # name, icon, description, optional `bricks:` list
python/main.py      # runs on Linux; entrypoint is App.run(...)
sketch/sketch.ino   # runs on the MCU (optional for Python-only apps)
sketch/sketch.yaml  # profiles -> platform: arduino:zephyr
```

**The Bridge** connects them:
- Sketch: `#include <Arduino_RouterBridge.h>`, then `Bridge.begin();` and
  `Bridge.provide("name", fn);` to expose callable providers.
- Python: `from arduino.app_utils import App, Bridge, Logger` (and `Frame`,
  `FrameDesigner`), then `Bridge.call("name", args)` (sync) or `Bridge.notify(...)`
  (fire-and-forget). Entrypoint: `App.run()` or `App.run(user_loop=fn)`.

Keep sketches thin (hardware I/O as providers); put logic in Python so you can iterate
without recompiling/reflashing.

## Running / deploying (as `craign` — the method that works)

Everything is driven by the **app daemon**: `arduino-app-cli daemon --port 8800` (systemd
`arduino-app-cli.service`), running as the `arduino` user with Docker + access to
`arduino-router` (which owns the MCU serial link `/dev/ttyHS1`). It listens on
`http://127.0.0.1:8800` and its API is reachable by **any local user** — so you deploy as
`craign` without ever being the `arduino` user.

**Use `./run.sh`** in the app folder (`./run.sh` to build+flash+run, `./run.sh stop` to
stop). It wraps these daemon calls:

- `GET  /v1/apps` — list; each `id` is `base64("<namespace>:<slug>")` (no `=` padding).
  Namespaces: `examples`, `user`, `local`.
- `GET  /v1/apps/{id}` — details incl. `status` and on-disk `path`.
- `POST /v1/apps/import?namespace=user&overwrite=true` — multipart form field
  **`file=@app.zip`**. Returns `{"id": ...}`. **The slug comes from the zip filename**, so
  name the zip deterministically (run.sh uses the folder name). The daemon copies the app
  into its own workspace and builds there → no permission hacks, no manual copying.
- `POST /v1/apps/{id}/start` — SSE stream of build/flash/run progress. The **id is a path
  segment** (not a query param). The app **persists after the stream closes** (it's a
  docker container); you only need the stream open during the build.
- `POST /v1/apps/{id}/stop` — stop. `DELETE /v1/apps/{id}` — remove.
- `GET  /v1/apps/{id}/logs` — SSE of the Python app's logs (or `docker logs <app>-main-1`).

Avoid the `arduino-app-cli` **CLI** for running: it's locked to the `arduino` user (UID
1000) and its `app start <path>` builds *in place* (needs a writable app dir). The daemon
API sidesteps both.

### `~/ArduinoApps`

Default per-user Arduino Apps workspace dir. **Empty and unused** with the daemon-API flow.
The daemon keeps its own built copy of imported apps under the `arduino` user, e.g.
`/home/arduino/ArduinoApps/<slug>/`. Safe to ignore.

## Onboard LED matrix

- **13 wide × 8 tall**, grayscale **3-bit** (per-pixel brightness `0..7`).
- Sketch: `#include <Arduino_LED_Matrix.h>`, `matrix.begin()`,
  `matrix.setGrayscaleBits(3)`, then `matrix.draw(buf)` where `buf` is 104 row-major
  brightness bytes.
- Python pushes a frame with `Bridge.call("draw", frame_bytes)` where `frame_bytes` is a
  `bytes` of length 104 (row-major, values 0–7). See `python/main.py` for the scroll
  approach; the board's `led-matrix-painter` example also shows animation buffering.

## Why there's Docker

App Lab / the daemon run each app's **Linux-side code, and every reusable "Brick", as
Docker containers**, orchestrated with docker-compose (see
`/var/lib/arduino-app-cli/assets/<ver>/compose/`):

- **Isolation & reproducibility** — each app gets its own pinned environment. This is why
  the `arduino.app_utils` / `arduino.app_bricks` Python SDK is **not** on the host `pip`;
  it lives inside the image.
- **Heavy stacks on demand** — Bricks (image classification, object detection, ASR/TTS,
  LLMs, Streamlit UIs) ship as prebuilt images from `ghcr.io/arduino/app-bricks/…`; you
  compose an app from bricks instead of hand-installing dependencies.
- **Lifecycle** — the daemon drives the Docker API to start/stop/health-check containers.

The **MCU sketch is not containerized** — it's cross-compiled for Zephyr and flashed to the
STM32. Docker is purely the Linux-side app runtime.

## Python SDK & Bricks

- `arduino.app_utils`: `App`, `Bridge`, `Frame`, `FrameDesigner`, `Logger`.
- `arduino.app_bricks.*`: reusable services, e.g. `web_ui.WebUI` (serves on port **7000**,
  `expose_api('GET'|'POST', path, handler)`), `dbstorage_sqlstore`, and many Edge-AI
  bricks. Declare them in `app.yaml` under `bricks:`.
- API docs on the board: `/var/lib/arduino-app-cli/assets/<ver>/api-docs/arduino/`.
- Example apps: `/var/lib/arduino-app-cli/examples/` (`blink`, `led-matrix-painter`,
  `color-your-leds`, …).

## Environment

- Develop as **`craign`** under `/home/craign`, git-tracked. `craign` is in the board
  groups needed for full capability: `docker, dialout, gpiod, video, audio, render, input,
  netdev, bluetooth, adm`. (To provision another user:
  `sudo usermod -aG docker,dialout,gpiod,video,audio,render,input,netdev,bluetooth,adm <user>`,
  then re-login. ⚠ `docker` group ≈ root-equivalent.)
- **git/GitHub:** `gh` is authenticated over HTTPS as `craignied` and set as git's
  credential helper — `git push`/`pull` and `gh …` work non-interactively.
- Board tooling: `arduino-app-cli` (daemon + arduino-only CLI), `arduino-cli`,
  `app-lab` (desktop GUI; needs a graphical session), `arduino-router`.

## Make a new project (recipe)

1. Copy this repo's shape into a new folder (the folder name becomes the app slug).
2. Edit `app.yaml`; write your `sketch/sketch.ino` providers and `python/main.py` logic.
3. `./run.sh` — import + build + flash + run, all as your own user.
