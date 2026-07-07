// Hello World Scroll — MCU (STM32U585 / Zephyr) side.
//
// Exposes a single Bridge provider, "draw", that receives one full LED-matrix
// frame (row-major, one brightness byte per pixel, 0..7) from the Python side
// and renders it. All scrolling/animation logic lives in python/main.py.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <vector>

Arduino_LED_Matrix matrix;

// Render a frame pushed from Python. `frame` is a row-major buffer of
// WIDTH*HEIGHT (13*8 = 104) brightness values in 0..7.
void draw(std::vector<uint8_t> frame) {
  if (frame.empty()) return;
  matrix.draw(frame.data());
}

void setup() {
  matrix.begin();
  // 3 grayscale bits -> the display accepts per-pixel brightness 0..7,
  // matching the values the Python side sends.
  matrix.setGrayscaleBits(3);
  matrix.clear();

  Bridge.begin();
  Bridge.provide("draw", draw);
}

void loop() {
  // Nothing to do here: frames arrive via the "draw" provider.
}
