// Bounded frame buffer shared by the sensor task (producer) and the network task (consumer).
// When full, the oldest frame is dropped and `dropped` is incremented. Not thread-safe on its
// own: main.cpp guards it with a FreeRTOS mutex.
#pragma once
#include <stdint.h>

#include "frame.h"

class FrameQueue {
 public:
  explicit FrameQueue(uint16_t capacity);
  ~FrameQueue();
  void push(const Frame &frame);
  uint16_t size() const { return size_; }
  uint16_t capacity() const { return capacity_; }
  // Copy up to `max` oldest frames into `out` without removing them.
  uint16_t peek(Frame *out, uint16_t max) const;
  // Remove the `count` oldest frames (after a successful send).
  void pop(uint16_t count);
  uint32_t dropped() const { return dropped_; }

 private:
  Frame *items_;
  uint16_t capacity_;
  uint16_t head_ = 0;  // oldest
  uint16_t size_ = 0;
  uint32_t dropped_ = 0;
};

// Retry delay after `failures` consecutive failures: 1, 2, 4, 8, 15, 15 ... seconds.
uint16_t backoff_seconds(uint16_t failures, uint16_t cap);
