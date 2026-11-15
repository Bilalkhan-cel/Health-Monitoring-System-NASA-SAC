// DS18B20 probe: one non-blocking conversion per second, raw reading only.
#pragma once
#include <Arduino.h>

class TemperatureProbe {
 public:
  void begin();
  // Call every loop. Updates the last reading when a conversion finishes.
  void poll();
  bool ok() const { return ok_; }
  float raw_c() const { return raw_c_; }
  uint8_t count() const { return count_; }

 private:
  uint32_t requested_ms_ = 0;
  bool pending_ = false;
  bool ok_ = false;
  float raw_c_ = 0.0f;
  float last_85_ = 0.0f;
  uint8_t count_ = 0;
};
