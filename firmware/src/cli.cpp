#include "cli.h"

#include <WiFi.h>
#include <Wire.h>

#include "config.h"
#include "frame_queue.h"
#include "net_client.h"
#include "pins.h"
#include "sensor_ds18b20.h"
#include "sensor_max30102.h"

namespace {
String line;

void print_help() {
  Serial.println("commands: status | scan | cal | ping | ip | server [url] | led | reboot");
}

void scan_i2c() {
  uint8_t found = 0;
  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  I2C device at 0x%02X%s\n", address, address == 0x57 ? "  (MAX30102)" : "");
      found++;
    }
  }
  if (found == 0) Serial.println("  no I2C device found: check wiring and the pull-up voltage (V3)");
}

void calibrate(PulseSensor &pulse) {
  Serial.println("  IR level now (no finger, then rest a finger on the sensor):");
  for (int i = 0; i < 10; i++) {
    Serial.printf("  IR %lu  red %lu\n", static_cast<unsigned long>(pulse.last_ir()),
                  static_cast<unsigned long>(pulse.last_red()));
    delay(500);
  }
  Serial.printf("  current thresholds: on > %d, off < %d (edit include/config.h)\n", FINGER_ON_IR, FINGER_OFF_IR);
}

void led_test() {
#if STATUS_LED_ENABLED
  Serial.printf("  blinking GPIO %d five times: if no LED lights up, this board has none there\n", PIN_STATUS_LED);
  for (int i = 0; i < 5; i++) {
    digitalWrite(PIN_STATUS_LED, HIGH);
    delay(200);
    digitalWrite(PIN_STATUS_LED, LOW);
    delay(200);
  }
#else
  Serial.println("  status LED disabled in pins.h");
#endif
}
}  // namespace

void cli_poll(NetClient &net, PulseSensor &pulse, TemperatureProbe &probe, FrameQueue &queue) {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c != '\n' && c != '\r') {
      if (line.length() < 200) line += c;
      continue;
    }
    line.trim();
    if (line.isEmpty()) continue;
    const String cmd = line;
    line = "";
    if (cmd == "status") {
      Serial.printf("  fw %s  wifi %s  rssi %d  ip %s\n", FW_VERSION,
                    WiFi.status() == WL_CONNECTED ? "connected" : "disconnected", WiFi.RSSI(),
                    WiFi.localIP().toString().c_str());
      Serial.printf("  server %s  last http %d  queue %u/%u  dropped %lu\n", net.server_url().c_str(),
                    net.last_status(), queue.size(), queue.capacity(), static_cast<unsigned long>(queue.dropped()));
      Serial.printf("  pulse sensor %s  IR %lu  red %lu  probe %s %.2f C (%u found)  heap %u\n",
                    pulse.present() ? "ok" : "MISSING", static_cast<unsigned long>(pulse.last_ir()),
                    static_cast<unsigned long>(pulse.last_red()), probe.ok() ? "ok" : "missing", probe.raw_c(),
                    probe.count(), ESP.getFreeHeap());
    } else if (cmd == "scan") {
      scan_i2c();
    } else if (cmd == "cal") {
      calibrate(pulse);
    } else if (cmd == "ping") {
      const bool ok = net.ping();
      Serial.printf("  ping %s -> %d\n", net.server_url().c_str(), net.last_status());
      if (!ok) Serial.println("  check the URL (server <url>), the firewall and client isolation");
    } else if (cmd == "ip") {
      Serial.printf("  %s\n", WiFi.localIP().toString().c_str());
    } else if (cmd.startsWith("server")) {
      const String url = cmd.substring(6);
      if (url.length() > 0) {
        String trimmed = url;
        trimmed.trim();
        net.set_server_url(trimmed);
        Serial.printf("  server stored: %s\n", net.server_url().c_str());
      } else {
        Serial.printf("  %s\n", net.server_url().c_str());
      }
    } else if (cmd == "led") {
      led_test();
    } else if (cmd == "reboot") {
      ESP.restart();
    } else {
      print_help();
    }
  }
}
