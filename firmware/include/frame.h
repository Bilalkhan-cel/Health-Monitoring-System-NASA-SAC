// One second of readings, exactly the fields of the HTTP contract (Appendix F).
#pragma once
#include <stdint.h>

#include "config.h"

enum FrameFlags : uint8_t {
  FLAG_I2C_ERROR = 1 << 0,
  FLAG_SENSOR_MISSING = 1 << 1,
};

struct Frame {
  uint32_t seq = 0;
  uint32_t up_ms = 0;
  bool finger = false;
  int16_t hr = -1;        // -1 = null
  int16_t spo2 = -1;      // -1 = null
  bool hr_ok = false;
  bool spo2_ok = false;
  float pi = 0.0f;
  int32_t ir_dc = 0;
  uint8_t q = 0;
  bool sat = false;
  float temp_c = 0.0f;
  bool temp_ok = false;
  uint8_t ppg_n = 0;
  int16_t ppg[SAMPLES_PER_FRAME] = {0};
  uint8_t flags = 0;
};
