# UNOq-hello

Scrolling **"HELLO WORLD"** on the onboard LED matrix of an **Arduino UNO Q**.

## About the board

The UNO Q is a hybrid board, not a classic microcontroller Arduino:

- **Linux side (MPU):** Qualcomm Dragonwing QRB2210, ARM Cortex-A53 (`aarch64`),
  running Debian 13. This is where the Python program runs.
- **Real-time side (MCU):** STM32U585 (Cortex-M33) running a Zephyr-based Arduino
  sketch. This drives the LED matrix hardware.

The two halves communicate over the Arduino **Router Bridge**. An "Arduino App"
bundles a Python program (`python/main.py`) and, optionally, a sketch
(`sketch/sketch.ino`) that RPC to each other across the Bridge.

The onboard LED matrix is 8 rows tall (the reference example uses a 13×8 grid),
grayscale at 3-bit depth (brightness 0–7). Python renders pixel frames and streams
them to the MCU over the Bridge, which calls `Arduino_LED_Matrix::draw()`.

## Project layout

This repo *is* an Arduino App:

```
app.yaml            # app name / icon / description
python/main.py      # runs on the Linux (MPU) side: renders + scrolls the text
sketch/sketch.ino   # runs on the MCU: exposes a "draw" Bridge provider
sketch/sketch.yaml  # targets the arduino:zephyr platform
CLAUDE.md           # detailed board/architecture notes and gotchas
README.md           # this file
```

## How it works

- **`sketch/sketch.ino`** (MCU) keeps it minimal: it registers one Router Bridge
  provider, `draw`, which takes a full frame — a row-major buffer of 13×8 = 104
  brightness bytes (0–7) — and hands it to `Arduino_LED_Matrix::draw()`.
- **`python/main.py`** (Linux) renders `"HELLO WORLD"` into a wide 1-bit bitmap using a
  built-in 5×7 font, then scrolls it by pushing one 13-wide window per tick via
  `Bridge.call("draw", frame_bytes)`. Tweak `SCROLL_MS` for speed and `MESSAGE` for the
  text (add glyphs to `FONT` for any new letters).

## Building & running

Apps are managed by `arduino-app-cli`, which **must run as the `arduino` user
(UID 1000)**, or through the App Lab GUI. See [`CLAUDE.md`](./CLAUDE.md) for the full
toolchain notes, the Python SDK (`arduino.app_utils` / `arduino.app_bricks`), the LED
matrix API, and environment caveats.

Reference examples live on the board under
`/var/lib/arduino-app-cli/examples/` — this app is modeled on `blink` (Bridge basics)
and `led-matrix-painter` (the LED matrix `draw` provider).
