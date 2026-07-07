# UNOq-hello

Scrolling **"HELLO WORLD"** across the onboard LED matrix of an **Arduino UNO Q** — a
"hello world" in the truest sense: it exercises every layer of this board's unusual stack
and proves the dev environment works end to end (Linux ↔ MCU bridge, the LED matrix, the
containerized app runtime, and the deploy path).

## The board in one paragraph

The UNO Q is **not** a classic microcontroller Arduino. It's a hybrid:

- **Linux side (MPU):** Qualcomm Dragonwing QRB2210, ARM Cortex-A53 (`aarch64`), running
  **Debian 13**. This is where you get a shell, and where the app's Python runs.
- **Real-time side (MCU):** an **STM32U585** running a **Zephyr**-based Arduino sketch that
  drives the hardware (LED matrix, GPIO, etc.).

The two halves talk over the Arduino **Router Bridge**. An "Arduino App" bundles a Python
program (`python/main.py`, runs on Linux) and a sketch (`sketch/sketch.ino`, runs on the
MCU) that RPC to each other across the Bridge.

## What this app does

- **`sketch/sketch.ino`** (MCU) is deliberately dumb: it registers one Bridge provider,
  `draw`, which takes a full frame — a row-major buffer of **13×8 = 104** brightness bytes
  (0–7) — and hands it to `Arduino_LED_Matrix::draw()`.
- **`python/main.py`** (Linux) renders `"HELLO WORLD"` into a wide 1-bit bitmap with a
  built-in 5×7 font, then scrolls it by pushing one 13-wide window per tick via
  `Bridge.call("draw", frame_bytes)`.

Because all the text logic lives in Python, you can change the message, speed, or
brightness **without recompiling the sketch**. Edit the constants at the top of
`python/main.py`: `MESSAGE`, `SCROLL_MS` (lower = faster), `ON` (brightness 0–7). Add new
letters by adding 5×7 glyphs to the `FONT` dict.

## Project layout

This repo *is* an Arduino App:

```
app.yaml            # app name / icon / description
python/main.py      # Linux (MPU) side: renders + scrolls the text
sketch/sketch.ino   # MCU side: exposes the "draw" Bridge provider
sketch/sketch.yaml  # targets the arduino:zephyr platform
CLAUDE.md           # deep board/architecture notes (read this for detail)
README.md           # this file
```

## Why there's Docker on this board

App Lab runs each app's **Linux-side code — and every reusable "Brick" — as Docker
containers**, orchestrated with docker-compose:

- **Isolation & reproducibility:** each app/brick gets its own pinned environment without
  polluting Debian. This is why the `arduino.app_utils` / `arduino.app_bricks` Python SDK
  is *not* on the host `pip` — it lives inside those images.
- **Heavy stacks on demand:** Bricks like image classification, object detection, ASR/TTS,
  and LLMs ship as prebuilt images pulled from `ghcr.io/arduino/app-bricks/…`. You compose
  an app from bricks instead of hand-installing gigabytes of dependencies.
- **Lifecycle:** the `arduino-app-cli` daemon drives the Docker API to start/stop/
  health-check those containers — which is why board users need to be in the `docker`
  group.

The **MCU sketch is not containerized** — it's cross-compiled for Zephyr and flashed to the
STM32. Docker is purely the Linux-side app runtime.

## Running it

The app is managed by the **`arduino-app-cli` daemon** (`arduino-app-cli.service`),
listening on `http://127.0.0.1:8800`.

**Easiest:** open **App Lab**, pick **"Hello World Scroll"**, hit Run. (It's already
importable there — see the deploy note below.)

**Headless / your own user:** the daemon's HTTP API is reachable by any local user, so you
can register the app as yourself without becoming the `arduino` user:

```bash
zip -r app.zip app.yaml python sketch
curl -X POST "http://127.0.0.1:8800/v1/apps/import?namespace=user&overwrite=true" \
     -F "file=@app.zip"          # → 201 {"id":"..."}  (shows up in App Lab)
```

Then Run from App Lab. (Triggering `run` purely over the API is still a TODO — see
Gotchas.)

## Gotchas & how-tos

These are the things that will bite you on this board — the whole point of a hello-world is
to surface them:

- **The CLI is single-seat, the daemon is not.** `arduino-app-cli` refuses to run unless
  you are user `arduino` (UID 1000); it's a statically linked binary, so that check can't
  be shimmed. **But** the real work is done by the daemon on `127.0.0.1:8800`, whose HTTP
  API any local user can call (see "Running it"). Don't assume you must *be* the arduino
  user — you don't.
- **Use your own user for projects.** Develop and `git` under `/home/craign` as normal. To
  get the actual board capability the `arduino` user has, add your user to the same groups:
  ```bash
  sudo usermod -aG docker,dialout,gpiod,video,audio,render,input,netdev,bluetooth,adm <you>
  ```
  then log out/in. `docker` → app containers (⚠ ≈ root-equivalent), `dialout` → MCU serial,
  `gpiod` → GPIO.
- **Matrix geometry.** This app assumes a **13-wide × 8-tall** matrix (matches Arduino's
  `led-matrix-painter` example). If the text looks horizontally wrong, change
  `MATRIX_WIDTH` in `python/main.py`. If it's upside-down, flip `ROW_OFFSET` / row order.
- **Brightness is 3-bit.** The sketch calls `matrix.setGrayscaleBits(3)`, so pixel values
  are `0..7`, not `0..255`. Frames are sent as plain row-major bytes.
- **App Lab needs a GUI session.** `app-lab` is a desktop (Wails) app; over a plain SSH
  shell it dies with "failed to init GTK". Use the board with a display, or its web UI.
- **Where the canonical examples live:** `/var/lib/arduino-app-cli/examples/` — this app is
  modeled on `blink` (Bridge basics) and `led-matrix-painter` (the matrix `draw` provider).
- **git/GitHub:** `gh` is installed and authenticated over HTTPS as `craignied` and set as
  git's credential helper, so `git push`/`pull` and `gh …` just work — no SSH keys, no
  token pasting.

For the full architecture, the Python SDK surface, and the daemon API map, see
[`CLAUDE.md`](./CLAUDE.md).
