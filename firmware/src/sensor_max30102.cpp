#include "sensor_max30102.h"

#include <MAX30105.h>
#include <Wire.h>
#include <spo2_algorithm.h>

#include "finger_detect.h"
#include "pins.h"
#include "signal_quality.h"

namespace {
MAX30105 chip;
FingerDetector finger(FINGER_ON_IR, FINGER_OFF_IR);
MedianFilter5 hr_filter;
MedianFilter5 spo2_filter;
}  // namespace

bool PulseSensor::begin() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(I2C_HZ);
  Wire.setTimeOut(200);  // never block the sensor task for long
  present_ = chip.begin(Wire, I2C_HZ);
  if (present_) {
    chip.setup(MAX_LED_BRIGHTNESS, MAX_SAMPLE_AVERAGE, MAX_LED_MODE, MAX_SAMPLE_RATE, MAX_PULSE_WIDTH,
               MAX_ADC_RANGE);
  }
  reset_window();
  return present_;
}

void PulseSensor::set_finger_levels(uint32_t on_level, uint32_t off_level) {
  finger.set_levels(on_level, off_level);
}

void PulseSensor::reset_window() {
  filled_ = 0;
  new_samples_ = 0;
  hr_filter.clear();
  spo2_filter.clear();
}

bool PulseSensor::poll(Frame &frame) {
  if (!present_) {
    // Retry every 5 s; meanwhile emit an empty frame each second so the server sees the problem.
    if (millis() - last_sample_ms_ >= 1000) {
      last_sample_ms_ = millis();
      static uint32_t last_retry = 0;
      if (millis() - last_retry > 5000) {
        last_retry = millis();
        begin();
      }
      frame.flags |= FLAG_SENSOR_MISSING | FLAG_I2C_ERROR;
      return true;
    }
    return false;
  }
  chip.check();
  bool got = false;
  while (chip.available()) {
    last_red_ = chip.getFIFORed();
    last_ir_ = chip.getFIFOIR();
    chip.nextSample();
    if (filled_ == WINDOW_SAMPLES) {
      memmove(ir_, ir_ + 1, (WINDOW_SAMPLES - 1) * sizeof(uint32_t));
      memmove(red_, red_ + 1, (WINDOW_SAMPLES - 1) * sizeof(uint32_t));
      filled_--;
    }
    ir_[filled_] = last_ir_;
    red_[filled_] = last_red_;
    filled_++;
    new_samples_++;
    got = true;
    last_sample_ms_ = millis();
    i2c_errors_ = 0;
  }
  if (!got && millis() - last_sample_ms_ > 500) {
    if (++i2c_errors_ >= I2C_ERROR_LIMIT) {
      frame.flags |= FLAG_I2C_ERROR;
      begin();  // re-initialise, bounded by Wire's 200 ms timeout
      i2c_errors_ = 0;
    }
    last_sample_ms_ = millis();
  }
  if (new_samples_ < SAMPLES_PER_FRAME) return false;
  new_samples_ = 0;

  const uint16_t start = filled_ - SAMPLES_PER_FRAME;
  const uint32_t mean_ir = mean_level(ir_ + start, SAMPLES_PER_FRAME);
  const bool was_on = finger.on();
  const bool on = finger.update(mean_ir);
  frame.finger = on;
  frame.ir_dc = static_cast<int32_t>(mean_ir);
  frame.sat = false;
  for (uint16_t i = start; i < filled_; i++) {
    if (ir_[i] >= SATURATION_IR) frame.sat = true;
  }
  frame.pi = perfusion_index(ir_ + start, SAMPLES_PER_FRAME);

  if (!on) {
    // Finger off: report nothing and forget everything, so no earlier value is ever reused.
    if (was_on) reset_window();
    filled_ = 0;
    frame.hr = frame.spo2 = -1;
    frame.hr_ok = frame.spo2_ok = false;
    frame.q = 0;
    frame.ppg_n = 0;
    return true;
  }
  if (!was_on) {
    reset_window();
    finger_on_ms_ = millis();
  }

#if SEND_PPG
  long dc = 0;
  for (uint16_t i = start; i < filled_; i++) dc += ir_[i];
  dc /= SAMPLES_PER_FRAME;
  frame.ppg_n = SAMPLES_PER_FRAME;
  for (uint16_t i = 0; i < SAMPLES_PER_FRAME; i++) {
    frame.ppg[i] = static_cast<int16_t>((static_cast<long>(ir_[start + i]) - dc) / 16);
  }
#endif

  // Report nothing until a full 4 s window plus SETTLE_S has passed since the finger arrived.
  const bool settled = filled_ == WINDOW_SAMPLES && millis() - finger_on_ms_ >= (4000 + SETTLE_S * 1000);
  if (!settled) {
    frame.hr = frame.spo2 = -1;
    frame.hr_ok = frame.spo2_ok = false;
    frame.q = quality_score(false, false, frame.pi, frame.sat, -1, -1);
    return true;
  }

  int32_t spo2 = 0, hr = 0;
  int8_t spo2_valid = 0, hr_valid = 0;
  maxim_heart_rate_and_oxygen_saturation(ir_, WINDOW_SAMPLES, red_, &spo2, &spo2_valid, &hr, &hr_valid);
  const bool hr_ok = hr_valid && hr != -999 && hr >= HR_MIN && hr <= HR_MAX;
  const bool spo2_ok = spo2_valid && spo2 != -999 && spo2 >= SPO2_MIN && spo2 <= SPO2_MAX;
  hr_filter.push(hr, hr_ok);
  spo2_filter.push(spo2, spo2_ok);
  frame.hr_ok = hr_filter.ready();
  frame.spo2_ok = spo2_filter.ready();
  frame.hr = frame.hr_ok ? static_cast<int16_t>(hr_filter.median()) : -1;
  frame.spo2 = frame.spo2_ok ? static_cast<int16_t>(spo2_filter.median()) : -1;
  frame.q = quality_score(frame.hr_ok, frame.spo2_ok, frame.pi, frame.sat, hr_ok ? hr : -1, frame.hr);
  return true;
}
