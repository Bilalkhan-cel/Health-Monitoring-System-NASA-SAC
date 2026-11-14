// AstroVital wearable: MAX30102 (pulse, SpO2) + DS18B20 (temperature) -> HTTP JSON at 1 Hz.
// The sensor task (core 1) never waits on the network; the network task (core 0) batches,
// retries and backs off. No clinical logic lives here: the server re-checks everything.

#include <Arduino.h>

#include "cli.h"
#include "config.h"
#include "frame_queue.h"
#include "net_client.h"
#include "pins.h"
#include "sensor_ds18b20.h"
#include "sensor_max30102.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "include/secrets.h is missing: run `python scripts/device_setup.py` first"
#endif

namespace {
PulseSensor pulse;
TemperatureProbe probe;
NetClient net;
FrameQueue queue(BUFFER_MAX);
SemaphoreHandle_t queue_lock;
uint32_t seq = 0;
String boot_id;
volatile bool beat = false;

void sensor_task(void *) {
  for (;;) {
    probe.poll();
    Frame frame;
    if (pulse.poll(frame)) {
      frame.seq = seq++;
      frame.up_ms = millis();
      frame.temp_ok = probe.ok();
      frame.temp_c = probe.raw_c();
      if (frame.hr_ok) beat = true;
      if (xSemaphoreTake(queue_lock, pdMS_TO_TICKS(20)) == pdTRUE) {
        queue.push(frame);
        xSemaphoreGive(queue_lock);
      }
    }
    vTaskDelay(pdMS_TO_TICKS(10));  // poll the FIFO every <= 20 ms
  }
}

void net_task(void *) {
  net.ping();
  for (;;) {
    net.step(queue, queue_lock);
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

// Status LED (mirrored to serial): slow blink = connecting, fast = server unreachable,
// three quick blinks = token rejected, pulse per heartbeat, off = idle.
void update_led() {
#if STATUS_LED_ENABLED
  static uint32_t last = 0;
  static NetState reported = NetState::OK;
  const uint32_t now = millis();
  const NetState state = net.state();
  if (state != reported) {
    reported = state;
    const char *names[] = {"connecting to Wi-Fi", "server unreachable", "token rejected", "ok"};
    Serial.printf("[led] %s\n", names[static_cast<int>(state)]);
  }
  bool on = false;
  switch (state) {
    case NetState::CONNECTING_WIFI: on = (now / 700) % 2; break;
    case NetState::SERVER_UNREACHABLE: on = (now / 150) % 2; break;
    case NetState::TOKEN_REJECTED: on = (now % 2000) < 600 && ((now % 2000) / 100) % 2 == 0; break;
    case NetState::OK:
      if (beat) {
        beat = false;
        last = now;
      }
      on = now - last < 80;
      break;
  }
  digitalWrite(PIN_STATUS_LED, on ? HIGH : LOW);
#endif
}
}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
#if STATUS_LED_ENABLED
  pinMode(PIN_STATUS_LED, OUTPUT);
#endif
  char id[9];
  snprintf(id, sizeof(id), "%08lx", static_cast<unsigned long>(esp_random()));
  boot_id = id;
  Serial.printf("\nAstroVital wearable fw %s  device %s  boot_id %s\n", FW_VERSION, DEVICE_ID, boot_id.c_str());
  if (pulse.begin()) {
    Serial.println("[sensor] MAX30102 found at 0x57");
  } else {
    Serial.println("[sensor] MAX30102 NOT found: run `scan`, check wiring (retrying every 5 s)");
  }
  probe.begin();
  Serial.printf("[sensor] DS18B20 count: %u\n", probe.count());
  queue_lock = xSemaphoreCreateMutex();
  net.begin(boot_id);
  xTaskCreatePinnedToCore(sensor_task, "sensor", 8192, nullptr, 2, nullptr, 1);
  xTaskCreatePinnedToCore(net_task, "net", 12288, nullptr, 1, nullptr, 0);
  Serial.println("type `status` for a summary, `help` for commands");
}

void loop() {
  cli_poll(net, pulse, probe, queue);
  update_led();
  static uint32_t last_heap = 0;
  if (millis() - last_heap > HEAP_REPORT_MS) {
    last_heap = millis();
    Serial.printf("[heap] free %u, queue %u\n", ESP.getFreeHeap(), queue.size());
  }
  delay(20);
}
