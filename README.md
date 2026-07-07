# UNOq-hello

Scrolling **"HELLO WORLD"** across the onboard LED matrix of an **Arduino UNO Q** — a
hello-world that exercises every layer of this board's unusual stack (Linux ↔ MCU bridge,
the LED matrix, the containerized app runtime) and doubles as a **working template** for
building your own UNO Q projects as your normal user.

> **Setting up a UNO Q from scratch?** Jump to
> [First-time board setup (soup to nuts)](#first-time-board-setup-soup-to-nuts) — unbox →
> App Lab → SSH → your own user → Claude Code, in order, exactly what worked on this board.

## First-time board setup (soup to nuts)

Everything below is one-time. The clean path uses **App Lab** *only* for first-boot
provisioning (it configures Wi-Fi and SSH for you), then you drop to SSH and never touch the
GUI again. This board is plain **Debian 13 (trixie), `aarch64`, ~3.6 GB RAM** — so keep it
**headless** (don't launch the UNO Q desktop) to leave RAM for actual builds.

### Phase 1 — Physical + App Lab provisioning (Mac, one time)

1. On your Mac (macOS 11+), download **App Lab** from Arduino's site and drag it to
   Applications.
2. Connect the UNO Q **directly** to the Mac with a **data-rated USB-C cable** — *not*
   through a hub. Apple USB-C hubs are explicitly incompatible and third-party hubs are
   flaky for first contact.
3. It powers on the instant it gets power (no button). Watch the LED matrix: a **swirling
   Arduino-logo** animation = booting; a **heartbeat/pulse** = ready (~30–60 s).
4. Open App Lab; it finds the board over USB (can take up to 60 s). Select it.
5. First-run wizard: set your **Linux account password**, name the board, pick your **Wi-Fi
   network** and enter its password. This is the important bit — App Lab configures Wi-Fi and
   sets up SSH for you.
6. Let it pull first-connect updates; restart App Lab if prompted. **After this you're done
   with the GUI.**

### Phase 2 — Get on the board headless (SSH)

Grab the board's IP (shown in App Lab) or use its mDNS hostname. From Mac Terminal:

```bash
ssh arduino@<board-ip>          # or ssh arduino@<boardname>.local
```

Password is what you set in the wizard (fresh-image default is `arduino`). Optionally
`ssh-copy-id arduino@<board-ip>` to skip the password next time.

### Phase 3 — Add your own user (don't fight the `arduino` default)

App Lab provisions the board around an `arduino` account and wires its tooling to it (apps
live under `/home/arduino/…`, SSH/provisioning target that user). That's a **board-image
convention, not a lock** — underneath it's plain Debian with full root. So don't fight it:
leave `arduino` alone as the "Arduino system" account (so App Lab keeps working) and add your
own user beside it for Claude Code and your work.

Still SSH'd in as `arduino`:

```bash
sudo adduser craign
sudo usermod -aG sudo craign
```

Then give that user **full board capability** — the groups the Arduino stack needs for
Docker, the MCU serial link, GPIO, video/audio, etc. (⚠ `docker` ≈ root-equivalent):

```bash
sudo usermod -aG docker,dialout,gpiod,video,audio,render,input,netdev,bluetooth,adm craign
```

From your Mac, drop your key on the new account, then live there:

```bash
ssh-copy-id craign@<board-ip>
ssh craign@<board-ip>           # log in as yourself from now on
```

Log out and back in (or reboot) so the new group memberships take effect.

### Phase 4 — Install Claude Code (as `craign`)

Freshen the OS, then run the native installer — it bundles its own runtime (no Node to
wrangle) and self-updates:

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://claude.ai/install.sh | bash
```

The installer drops `claude` in `~/.local/bin`. **Make sure that's on your PATH** — and that
it's *your* home, not the `arduino` user's (that exact mixup cost time here):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
claude --version    # confirm it resolves to /home/craign/.local/bin/claude
```

Start it in whatever project dir you want:

```bash
claude
```

On first launch it prints a login URL. Since you're SSH'd in, open that URL in your **Mac's**
browser, approve, and paste the code back into the terminal.

> **Notes.** Claude Code needs a paid plan (Pro/Max/Team/Enterprise or API/Console) — the
> free tier doesn't include it. The `apt` route is a legit alternative to the curl script
> (Anthropic publishes a signed apt repo that rides your normal `apt upgrade`); the native
> installer is one line and self-updating, so start there.

### Phase 5 — You're in

You're now `craign` on the Linux side with Claude Code, Docker, and MCU access. Clone this
repo and go:

```bash
git clone https://github.com/craignied/UNOq-hello.git
cd UNOq-hello
./run.sh
```

That builds, flashes the MCU, and scrolls HELLO WORLD. Continue with [Run it](#run-it) below.

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

### Auto-start on boot

A deployed app does **not** restart itself after you unplug/replug the board — it's a
container created with restart policy `no`, and the daemon only auto-launches the one app
marked as **default** at boot. To make this app come up on power-up, flag it:

```bash
curl -s -X PATCH http://127.0.0.1:8800/v1/apps/dXNlcjpoZWxsbw \
  -H 'Content-Type: application/json' -d '{"default": true}'
```

The id `dXNlcjpoZWxsbw` is `base64("user:hello")`; `{"default": false}` undoes it. The flag
is stored in the daemon's app metadata, so it **survives `./run.sh` redeploys**. On the
first boot after flagging, the app still builds/flashes the MCU sketch, so give it a minute.

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
- **Nothing auto-starts after a power-cycle** unless you mark the app as the board's
  **default**. See [Auto-start on boot](#auto-start-on-boot).
- **git/GitHub:** `gh` is authenticated over HTTPS, so `git push`/`pull` just work.
