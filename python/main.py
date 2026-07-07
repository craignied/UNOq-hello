# Hello World Scroll — Linux (Qualcomm MPU) side.
#
# Renders "HELLO WORLD" into a wide 1-bit bitmap and scrolls it across the
# onboard LED matrix by pushing one 13x8 frame at a time to the MCU over the
# Router Bridge (the sketch's "draw" provider calls Arduino_LED_Matrix::draw).

from arduino.app_utils import App, Bridge, Logger
import time

# --- Matrix / display parameters ---------------------------------------------
MATRIX_WIDTH = 13      # columns on the onboard matrix (per led-matrix-painter)
MATRIX_HEIGHT = 8      # rows
ON = 7                 # brightness of a lit pixel (0..7; sketch uses 3 grayscale bits)
OFF = 0
SCROLL_MS = 90         # delay between one-column shifts (lower = faster)

MESSAGE = "HELLO WORLD"

logger = Logger("hello-scroll")

# --- 5x7 font (only the glyphs used by MESSAGE) ------------------------------
# Each glyph is 7 strings (top row first); '1' = lit pixel, '0' = off.
FONT = {
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
}
GLYPH_ROWS = 7
ROW_OFFSET = 0         # top row where the 7-tall glyph sits (0 => bottom row blank)
LETTER_SPACING = 1     # blank columns between letters
SPACE_WIDTH = 3        # width of a ' ' character


def build_columns(message):
    """Build the full scrolling bitmap as a list of columns.

    Each column is a list of MATRIX_HEIGHT brightness values (top row first).
    """
    blank = lambda: [OFF] * MATRIX_HEIGHT
    cols = []
    for ch in message:
        if ch == " ":
            cols.extend(blank() for _ in range(SPACE_WIDTH))
            continue
        glyph = FONT[ch]
        for c in range(len(glyph[0])):
            column = blank()
            for r in range(GLYPH_ROWS):
                if glyph[r][c] == "1":
                    column[ROW_OFFSET + r] = ON
            cols.append(column)
        cols.extend(blank() for _ in range(LETTER_SPACING))
    return cols


# Build once at startup. Append a full blank screen so the message scrolls
# completely off before it wraps around and repeats.
columns = build_columns(MESSAGE)
columns.extend([OFF] * MATRIX_HEIGHT for _ in range(MATRIX_WIDTH))
total_columns = len(columns)
offset = 0

logger.info(
    f"Scrolling '{MESSAGE}': {total_columns} columns on "
    f"{MATRIX_WIDTH}x{MATRIX_HEIGHT} matrix, {SCROLL_MS}ms/step"
)


def render_frame(start):
    """Return the row-major byte buffer for the MATRIX_WIDTH-wide window
    beginning at column `start` (wrapping around the message)."""
    buf = bytearray(MATRIX_WIDTH * MATRIX_HEIGHT)
    i = 0
    for r in range(MATRIX_HEIGHT):
        for c in range(MATRIX_WIDTH):
            buf[i] = columns[(start + c) % total_columns][r]
            i += 1
    return bytes(buf)


def loop():
    global offset
    Bridge.call("draw", render_frame(offset))
    offset = (offset + 1) % total_columns
    time.sleep(SCROLL_MS / 1000.0)


App.run(user_loop=loop)
