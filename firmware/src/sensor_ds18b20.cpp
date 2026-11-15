#include "sensor_ds18b20.h"

#include <DallasTemperature.h>
#include <OneWire.h>

#include "config.h"
#include "pins.h"

namespace {
OneWire bus(PIN_ONEWIRE);
DallasTemperature sensors(&bus);
}  // namespace

void TemperatureProbe::begin() {
  sensors.begin();
  sensors.setResolution(TEMP_RESOLUTION_BITS);
  sensors.setWaitForConversion(false);
  count_ = sensors.getDeviceCount();
}

void TemperatureProbe::poll() {
  const uint32_t now = millis();
  if (!pending_) {
    sensors.requestTemperatures();
    requested_ms_ = now;
    pending_ = true;
    return;
  }
  if (now - requested_ms_ < TEMP_READ_DELAY_MS) return;
  pending_ = false;
  const float value = sensors.getTempCByIndex(0);
  if (value == DEVICE_DISCONNECTED_C) {  // -127: probe unplugged
    ok_ = false;
    count_ = 0;
    sensors.begin();  // look for the probe again
    count_ = sensors.getDeviceCount();
    return;
  }
  if (value == 85.0f) {
    // Power-on default: only trust 85.0 when two consecutive readings agree.
    if (last_85_ == 85.0f) {
      ok_ = true;
      raw_c_ = value;
    }
    last_85_ = value;
    return;
  }
  last_85_ = value;
  if (value < TEMP_MIN_C || value > TEMP_MAX_C) {
    ok_ = false;
    return;
  }
  ok_ = true;
  raw_c_ = value;
}
