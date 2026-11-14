// Smoothing and the 0-100 quality score sent with every frame (Section 10A.3).
#pragma once
#include <stdint.h>

// Median of the last 5 valid values; publishes only when at least 3 of the last 5 were valid.
class MedianFilter5 {
 public:
  void push(int32_t value, bool valid);
  bool ready() const;       // >= 3 of the last 5 valid
  int32_t median() const;   // median of the valid values in the window
  void clear();

 private:
  int32_t values_[5] = {0};
  bool valid_[5] = {false};
  uint8_t next_ = 0;
  uint8_t count_ = 0;
};

// q = 50 if both flags valid + 25 if 0.3 <= pi <= 10 + 10 if not saturated + 15 if |hr - median| <= 10.
uint8_t quality_score(bool hr_ok, bool spo2_ok, float pi, bool saturated, int32_t hr, int32_t hr_median);

// Perfusion index: (IR peak-to-peak in the window / mean IR) x 100.
float perfusion_index(const uint32_t *ir, uint16_t count);

// Mean IR level of a window (finger detection input and the ir_dc field).
uint32_t mean_level(const uint32_t *values, uint16_t count);
