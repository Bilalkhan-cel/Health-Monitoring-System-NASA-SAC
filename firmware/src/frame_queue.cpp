#include "frame_queue.h"

FrameQueue::FrameQueue(uint16_t capacity) : items_(new Frame[capacity]), capacity_(capacity) {}

FrameQueue::~FrameQueue() { delete[] items_; }

void FrameQueue::push(const Frame &frame) {
  if (size_ == capacity_) {
    head_ = (head_ + 1) % capacity_;
    size_--;
    dropped_++;
  }
  items_[(head_ + size_) % capacity_] = frame;
  size_++;
}

uint16_t FrameQueue::peek(Frame *out, uint16_t max) const {
  const uint16_t n = size_ < max ? size_ : max;
  for (uint16_t i = 0; i < n; i++) out[i] = items_[(head_ + i) % capacity_];
  return n;
}

void FrameQueue::pop(uint16_t count) {
  if (count > size_) count = size_;
  head_ = (head_ + count) % capacity_;
  size_ -= count;
}

uint16_t backoff_seconds(uint16_t failures, uint16_t cap) {
  if (failures == 0) return 0;
  uint32_t delay = 1u << (failures - 1 > 4 ? 4 : failures - 1);
  return delay > cap ? cap : static_cast<uint16_t>(delay);
}
