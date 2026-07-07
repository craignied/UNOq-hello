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

```
CLAUDE.md   # detailed board/architecture notes and gotchas
README.md   # this file
```

The scrolling-text app (`app.yaml`, `python/main.py`, `sketch/sketch.ino`) will be
added here.

## Building & running

Apps are managed by `arduino-app-cli`, which **must run as the `arduino` user
(UID 1000)**, or through the App Lab GUI. See [`CLAUDE.md`](./CLAUDE.md) for the full
toolchain notes, the Python SDK (`arduino.app_utils` / `arduino.app_bricks`), the LED
matrix API, and environment caveats.

Reference examples live on the board under
`/var/lib/arduino-app-cli/examples/` — see `blink` and `led-matrix-painter`.
