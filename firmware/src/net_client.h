// Wi-Fi + HTTP client: batches frames to /api/device/ingest with backoff, discovery and
// the reactions of Appendix F (401 stop, 4xx drop, 429/503 honour Retry-After, 5xx retry).
#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "frame_queue.h"

enum class NetState : uint8_t { CONNECTING_WIFI, SERVER_UNREACHABLE, TOKEN_REJECTED, OK };

class NetClient {
 public:
  void begin(const String &boot_id);
  // Run one step of the network task; never blocks longer than the HTTP timeout.
  void step(FrameQueue &queue, SemaphoreHandle_t lock);
  bool ping();
  NetState state() const { return state_; }
  const String &server_url() const { return server_url_; }
  void set_server_url(const String &url);  // stored in flash (Preferences)
  int last_status() const { return last_status_; }
  uint32_t send_interval_ms() const { return send_interval_ms_; }

 private:
  void ensure_wifi();
  bool discover();
  int post_batch(const Frame *frames, uint16_t count, uint32_t dropped);

  String boot_id_;
  String server_url_;
  NetState state_ = NetState::CONNECTING_WIFI;
  uint32_t next_attempt_ms_ = 0;
  uint32_t first_failure_ms_ = 0;
  uint16_t failures_ = 0;
  uint8_t ping_failures_ = 0;
  uint32_t wifi_lost_ms_ = 0;
  uint32_t send_interval_ms_ = SEND_INTERVAL_MS;
  int last_status_ = 0;
  uint16_t batch_limit_ = MAX_BATCH;
};
