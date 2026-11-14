// MAX30102 pulse/SpO2 sensor: FIFO polling, 4 s windows, Maxim algorithm, smoothing, quality.
#pragma once
#include <Arduino.h>

#include "frame.h"

class PulseSensor {
 public:
  bool begin();                    // false if the chip does not answer at 0x57
  bool present() const { return present_; }
  // Poll the FIFO (call at least every 20 ms). Returns true when a 1 s frame is complete
  // and has been written into `frame` (pulse fields only).
  bool poll(Frame &frame);
  void set_finger_levels(uint32_t on_level, uint32_t off_level);
  uint32_t last_ir() const { return last_ir_; }
  uint32_t last_red() const { return last_red_; }
  void reset_window();

 private:
  bool present_ = false;
  uint32_t ir_[WINDOW_SAMPLES] = {0};
  uint32_t red_[WINDOW_SAMPLES] = {0};
  uint16_t filled_ = 0;            // samples in the rolling window
  uint16_t new_samples_ = 0;       // samples since the last frame
  uint32_t finger_on_ms_ = 0;
  uint32_t last_ir_ = 0;
  uint32_t last_red_ = 0;
  uint8_t i2c_errors_ = 0;
  uint32_t last_sample_ms_ = 0;
};
