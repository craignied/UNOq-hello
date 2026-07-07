# UNOq-hello

Scrolling **"HELLO WORLD"** across the onboard LED matrix of an **Arduino UNO Q** — a
hello-world that exercises every layer of this board's unusual stack (Linux ↔ MCU bridge,
the LED matrix, the containerized app runtime) and doubles as a **working template** for
building your own UNO Q projects as your normal user.

## Run it

From this directory, as your normal user (`craign`):

```bash
./run.sh          # build, flash the MCU, and start the app
./run.sh stop     # stop it
```

That's the whole workflow: edit the code in this repo, run `./run.sh`. The app keeps
running after the script exits (it's a container the board manages), so `stop` when you're
done. The **first** run takes a few minutes (it compiles the sketch and flashes the
microcontroller); later runs are quick.

No `sudo`, no `arduino` user, no App Lab, and nothing gets copied out of this folder —
`run.sh` hands the app to the board's app daemon over its local HTTP API, and the daemon
does the privileged work. See [How deployment works](#how-deployment-works).

## What it does

- **`sketch/sketch.ino`** runs on the **MCU**. It's deliberately minimal: it registers one
  Bridge provider, `draw`, which takes a full frame — a row-major buffer of **13×8 = 104**
  brightness bytes (0–7) — and hands it to `Arduino_LED_Matrix::draw()`.
- **`python/main.py`** runs on **Linux**. It renders `"HELLO WORLD"` into a wide 1-bit
  bitmap with a built-in 5×7 font, then scrolls it by pushing one 13-wide window per tick
  via `Bridge.call("draw", frame_bytes)`.

Because the text logic lives in Python, you can change things **without recompiling the
sketch** — edit the constants at the top of `python/main.py`: `MESSAGE`, `SCROLL_MS`
(lower = faster), `ON` (brightness 0–7). Add letters by adding 5×7 glyphs to `FONT`.

## The board in one paragraph

The UNO Q is **not** a classic microcontroller Arduino. It's a hybrid:

- **Linux side (MPU):** Qualcomm Dragonwing QRB2210, ARM Cortex-A53 (`aarch64`), running
  **Debian**. You get a shell here; the app's Python runs here.
- **Real-time side (MCU):** an **STM32U585** running a **Zephyr**-based Arduino sketch that
  drives the hardware.

The two halves talk over the Arduino **Router Bridge**: the sketch registers callable
providers with `Bridge.provide(...)`, and Python calls them with `Bridge.call(...)`.

## How deployment works

The board runs an **app daemon** (`arduino-app-cli daemon`, systemd
`arduino-app-cli.service`) on `http://127.0.0.1:8800`. It runs as the `arduino` user with
Docker and MCU access, and does all the real work. Its HTTP API is reachable by **any
local user**, so you never have to *be* the `arduino` user. `run.sh` is a thin wrapper
around two calls:

1. **Import** — `POST /v1/apps/import` with a zip of this folder. The daemon copies the app
   into its own workspace and owns the build directory, so there are **no file-permission
   problems** — this is why nothing needs copying by hand.
2. **Start** — `POST /v1/apps/{id}/start`. The daemon compiles the sketch, flashes the MCU,
   and starts the Python container. The app then keeps running on its own.

> Note: there is also an `arduino-app-cli app start <path>` CLI command, but it is locked to
> the `arduino` user *and* builds in place (needing a writable app dir). Prefer the daemon
> API / `run.sh` — it avoids both problems.

### What is `~/ArduinoApps`?

It's the default per-user Arduino Apps workspace folder. In your home it's **empty and
unused** by this workflow — the daemon keeps its own built copy of imported apps under the
`arduino` user (e.g. `/home/arduino/ArduinoApps/hello/`). You can ignore `~/ArduinoApps`.

## Project layout

This repo *is* an Arduino App:

```
run.sh              # build + flash + run, as your own user (start | stop)
app.yaml            # app name / icon / description
python/main.py      # Linux side: renders + scrolls the text
sketch/sketch.ino   # MCU side: the "draw" Bridge provider
sketch/sketch.yaml  # targets the arduino:zephyr platform
CLAUDE.md           # deeper board/architecture reference
```

## Make your own project

Copy this repo's shape and change three files:

1. **`app.yaml`** — name/icon/description.
2. **`sketch/sketch.ino`** — expose whatever hardware operations you need as
   `Bridge.provide("name", fn)` handlers (keep it thin; put logic in Python).
3. **`python/main.py`** — your logic, calling the sketch via `Bridge.call(...)` /
   `Bridge.notify(...)`, with `App.run(user_loop=...)` as the entrypoint.

Then `./run.sh`. The daemon derives the app's id from the **zip filename**, which `run.sh`
sets from the folder name — so keep the folder name stable, or set `SLUG=` when invoking.
More detail (Python SDK, Bricks, LED-matrix format, Docker's role) is in
[`CLAUDE.md`](./CLAUDE.md); canonical examples live on the board under
`/var/lib/arduino-app-cli/examples/` (`blink`, `led-matrix-painter`).

## Gotchas worth knowing

- **Matrix is 13×8, brightness 0–7** (3 grayscale bits). Frames are plain row-major bytes.
- **Develop as your own user.** To have full board capability, your user needs the right
  groups (`docker`, `dialout`, `gpiod`, …) — see [`CLAUDE.md`](./CLAUDE.md). `docker` group
  access is effectively root-equivalent.
- **The Python SDK isn't on the host `pip`** — it lives inside the app's container image
  (that's what Docker is for here). Import `arduino.app_utils` / `arduino.app_bricks` from
  within the app, not from a host shell.
- **git/GitHub:** `gh` is authenticated over HTTPS, so `git push`/`pull` just work.
