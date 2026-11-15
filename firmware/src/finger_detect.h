// Finger detection with hysteresis on the mean IR level of the last frame.
#pragma once
#include <stdint.h>

class FingerDetector {
 public:
  FingerDetector(uint32_t on_level, uint32_t off_level) : on_level_(on_level), off_level_(off_level) {}
  // Returns the new state. On above `on_level`, off below `off_level`, otherwise unchanged.
  bool update(uint32_t mean_ir);
  bool on() const { return on_; }
  void set_levels(uint32_t on_level, uint32_t off_level) { on_level_ = on_level; off_level_ = off_level; }

 private:
  uint32_t on_level_;
  uint32_t off_level_;
  bool on_ = false;
};
