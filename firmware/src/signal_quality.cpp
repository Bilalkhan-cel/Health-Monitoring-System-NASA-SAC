#include "signal_quality.h"

#include <stdlib.h>

void MedianFilter5::push(int32_t value, bool valid) {
  values_[next_] = value;
  valid_[next_] = valid;
  next_ = (next_ + 1) % 5;
  if (count_ < 5) count_++;
}

bool MedianFilter5::ready() const {
  uint8_t valid = 0;
  for (uint8_t i = 0; i < count_; i++) valid += valid_[i] ? 1 : 0;
  return valid >= 3;
}

int32_t MedianFilter5::median() const {
  int32_t sorted[5];
  uint8_t n = 0;
  for (uint8_t i = 0; i < count_; i++) {
    if (valid_[i]) sorted[n++] = values_[i];
  }
  if (n == 0) return -1;
  for (uint8_t i = 1; i < n; i++) {
    int32_t key = sorted[i];
    int8_t j = i - 1;
    while (j >= 0 && sorted[j] > key) {
      sorted[j + 1] = sorted[j];
      j--;
    }
    sorted[j + 1] = key;
  }
  return sorted[n / 2];
}

void MedianFilter5::clear() {
  for (uint8_t i = 0; i < 5; i++) valid_[i] = false;
  next_ = 0;
  count_ = 0;
}

uint8_t quality_score(bool hr_ok, bool spo2_ok, float pi, bool saturated, int32_t hr, int32_t hr_median) {
  uint8_t q = 0;
  if (hr_ok && spo2_ok) q += 50;
  if (pi >= 0.3f && pi <= 10.0f) q += 25;
  if (!saturated) q += 10;
  if (hr_ok && hr_median > 0 && labs(static_cast<long>(hr - hr_median)) <= 10) q += 15;
  return q;
}

float perfusion_index(const uint32_t *ir, uint16_t count) {
  if (count == 0) return 0.0f;
  uint32_t lo = ir[0], hi = ir[0];
  uint64_t sum = 0;
  for (uint16_t i = 0; i < count; i++) {
    if (ir[i] < lo) lo = ir[i];
    if (ir[i] > hi) hi = ir[i];
    sum += ir[i];
  }
  const double mean = static_cast<double>(sum) / count;
  if (mean <= 0.0) return 0.0f;
  return static_cast<float>((hi - lo) / mean * 100.0);
}

uint32_t mean_level(const uint32_t *values, uint16_t count) {
  if (count == 0) return 0;
  uint64_t sum = 0;
  for (uint16_t i = 0; i < count; i++) sum += values[i];
  return static_cast<uint32_t>(sum / count);
}
