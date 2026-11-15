#include "net_client.h"

#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>

#include "config.h"
#include "secrets.h"

namespace {
Preferences prefs;
Frame batch_buf[MAX_BATCH];

void on_wifi_event(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    Serial.printf("[wifi] disconnected, reason %d\n", info.wifi_sta_disconnected.reason);
  } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    Serial.printf("[wifi] connected, ip %s\n", WiFi.localIP().toString().c_str());
  }
}
}  // namespace

void NetClient::begin(const String &boot_id) {
  boot_id_ = boot_id;
  prefs.begin("astrovital", false);
  server_url_ = prefs.getString("server", SERVER_URL);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.onEvent(on_wifi_event);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void NetClient::set_server_url(const String &url) {
  server_url_ = url;
  while (server_url_.endsWith("/")) server_url_.remove(server_url_.length() - 1);
  prefs.putString("server", server_url_);
}

void NetClient::ensure_wifi() {
  if (WiFi.status() == WL_CONNECTED) {
    wifi_lost_ms_ = 0;
    return;
  }
  state_ = NetState::CONNECTING_WIFI;
  const uint32_t now = millis();
  if (wifi_lost_ms_ == 0) wifi_lost_ms_ = now;
  static uint32_t last_force = 0;
  if (now - wifi_lost_ms_ > WIFI_FORCE_RECONNECT_MS && now - last_force > WIFI_FORCE_RECONNECT_MS) {
    last_force = now;
    WiFi.disconnect();
    WiFi.reconnect();
  }
  if (now - wifi_lost_ms_ > WIFI_RESTART_MS) {
    Serial.println("[wifi] offline for 5 minutes, restarting");
    ESP.restart();
  }
}

bool NetClient::discover() {
  if (!MDNS.begin("astrovital-wearable")) return false;
  const int found = MDNS.queryService("astrovital", "tcp");
  if (found <= 0) return false;
  const String url = "http://" + MDNS.IP(0).toString() + ":" + String(MDNS.port(0));
  Serial.printf("[net] discovered server %s\n", url.c_str());
  set_server_url(url);
  return true;
}

bool NetClient::ping() {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setReuse(false);
  if (!http.begin(server_url_ + "/api/device/ping")) return false;
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  http.addHeader("X-Device-Id", DEVICE_ID);
  const int status = http.GET();
  http.end();
  last_status_ = status;
  if (status == 401) state_ = NetState::TOKEN_REJECTED;
  if (status == 200) {
    ping_failures_ = 0;
    state_ = NetState::OK;
    return true;
  }
  if (++ping_failures_ >= PING_FAILS_BEFORE_MDNS) {
    ping_failures_ = 0;
    discover();
  }
  return false;
}

int NetClient::post_batch(const Frame *frames, uint16_t count, uint32_t dropped) {
  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["fw"] = FW_VERSION;
  doc["boot_id"] = boot_id_;
  doc["sent_uptime_ms"] = millis();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["dropped"] = dropped;
  JsonArray list = doc["frames"].to<JsonArray>();
  for (uint16_t i = 0; i < count; i++) {
    const Frame &f = frames[i];
    JsonObject o = list.add<JsonObject>();
    o["seq"] = f.seq;
    o["up_ms"] = f.up_ms;
    o["finger"] = f.finger;
    if (f.hr >= 0) o["hr"] = f.hr; else o["hr"] = nullptr;
    if (f.spo2 >= 0) o["spo2"] = f.spo2; else o["spo2"] = nullptr;
    o["hr_ok"] = f.hr_ok;
    o["spo2_ok"] = f.spo2_ok;
    o["pi"] = serialized(String(f.pi, 2));
    o["ir_dc"] = f.ir_dc;
    o["q"] = f.q;
    o["sat"] = f.sat;
    if (f.temp_ok) o["temp_c"] = serialized(String(f.temp_c, 2)); else o["temp_c"] = nullptr;
    o["temp_ok"] = f.temp_ok;
    if (f.ppg_n > 0) {
      JsonArray ppg = o["ppg"].to<JsonArray>();
      for (uint8_t k = 0; k < f.ppg_n; k++) ppg.add(f.ppg[k]);
    }
    JsonArray flags = o["flags"].to<JsonArray>();
    if (f.flags & FLAG_I2C_ERROR) flags.add("i2c_error");
    if (f.flags & FLAG_SENSOR_MISSING) flags.add("sensor_missing");
  }
  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setReuse(false);  // do not rely on keep-alive
  if (!http.begin(server_url_ + "/api/device/ingest")) return -1;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  http.addHeader("X-Device-Id", DEVICE_ID);
  const char *keep[] = {"Retry-After"};
  http.collectHeaders(keep, 1);
  const int status = http.POST(body);
  if (status == 200) {
    JsonDocument reply;
    if (!deserializeJson(reply, http.getString())) {
      const uint32_t interval = reply["cfg"]["send_interval_ms"] | SEND_INTERVAL_MS;
      if (interval >= 250 && interval <= 10000) send_interval_ms_ = interval;
    }
  } else if (status == 429 || status == 503) {
    const int retry = http.header("Retry-After").toInt();
    next_attempt_ms_ = millis() + static_cast<uint32_t>((retry > 0 ? retry : 5) * 1000);
  }
  http.end();
  return status;
}

void NetClient::step(FrameQueue &queue, SemaphoreHandle_t lock) {
  ensure_wifi();
  if (WiFi.status() != WL_CONNECTED) return;
  if (state_ == NetState::TOKEN_REJECTED) return;  // stop sending; do not hammer the server
  const uint32_t now = millis();
  if (now < next_attempt_ms_) return;

  uint16_t count = 0;
  uint32_t dropped = 0;
  if (xSemaphoreTake(lock, pdMS_TO_TICKS(50)) == pdTRUE) {
    count = queue.peek(batch_buf, batch_limit_);
    dropped = queue.dropped();
    xSemaphoreGive(lock);
  }
  if (count == 0) {
    next_attempt_ms_ = now + send_interval_ms_;
    return;
  }
  const int status = post_batch(batch_buf, count, dropped);
  last_status_ = status;
  if (status >= 200 && status < 300) {
    if (xSemaphoreTake(lock, pdMS_TO_TICKS(50)) == pdTRUE) {
      queue.pop(count);
      xSemaphoreGive(lock);
    }
    failures_ = 0;
    first_failure_ms_ = 0;
    batch_limit_ = MAX_BATCH;
    state_ = NetState::OK;
    // Catch up quickly when frames are queued, otherwise send once per interval.
    next_attempt_ms_ = millis() + (queue.size() > 0 ? 50 : send_interval_ms_);
    return;
  }
  if (status == 401) {
    state_ = NetState::TOKEN_REJECTED;
    Serial.println("[net] token rejected: run device_setup.py and re-flash");
    return;
  }
  if (status == 413) {
    batch_limit_ = batch_limit_ > 1 ? batch_limit_ / 2 : 1;
    return;
  }
  if (status == 429 || status == 503) return;  // next_attempt_ms_ set from Retry-After
  if (status >= 400 && status < 500) {
    // Malformed batch: drop it so it cannot block the queue.
    if (xSemaphoreTake(lock, pdMS_TO_TICKS(50)) == pdTRUE) {
      queue.pop(count);
      xSemaphoreGive(lock);
    }
    Serial.printf("[net] batch rejected with %d, dropped\n", status);
    return;
  }
  // 5xx, timeout, DNS or connect failure: keep the frames and back off.
  state_ = NetState::SERVER_UNREACHABLE;
  failures_++;
  if (first_failure_ms_ == 0) first_failure_ms_ = now;
  next_attempt_ms_ = millis() + backoff_seconds(failures_, BACKOFF_CAP_S) * 1000UL;
  if (millis() - first_failure_ms_ > REDISCOVER_AFTER_MS) {
    first_failure_ms_ = millis();
    discover();
  }
}
