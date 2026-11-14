// Pure-logic tests that run on the host: pio test -d firmware -e native
#include <unity.h>

#include "../../src/finger_detect.h"
#include "../../src/frame_queue.h"
#include "../../src/signal_quality.h"

void setUp() {}
void tearDown() {}

void test_finger_hysteresis() {
  FingerDetector finger(50000, 30000);
  TEST_ASSERT_FALSE(finger.update(40000));  // between thresholds, starts off
  TEST_ASSERT_TRUE(finger.update(60000));   // above on-level
  TEST_ASSERT_TRUE(finger.update(40000));   // between thresholds stays on
  TEST_ASSERT_FALSE(finger.update(20000));  // below off-level
  TEST_ASSERT_FALSE(finger.update(45000));  // stays off until above on-level
}

void test_median_needs_three_of_five() {
  MedianFilter5 filter;
  filter.push(70, true);
  filter.push(0, false);
  TEST_ASSERT_FALSE(filter.ready());
  filter.push(74, true);
  filter.push(72, true);
  TEST_ASSERT_TRUE(filter.ready());
  TEST_ASSERT_EQUAL_INT32(72, filter.median());
  filter.push(200, true);
  filter.push(0, false);
  filter.push(0, false);
  TEST_ASSERT_TRUE(filter.ready());
  filter.clear();
  TEST_ASSERT_FALSE(filter.ready());
}

void test_quality_score() {
  TEST_ASSERT_EQUAL_UINT8(100, quality_score(true, true, 1.8f, false, 72, 74));
  TEST_ASSERT_EQUAL_UINT8(35, quality_score(false, false, 1.8f, false, -1, -1));
  TEST_ASSERT_EQUAL_UINT8(75, quality_score(true, true, 0.1f, false, 72, 74) + 0);
}

void test_queue_drops_the_oldest_when_full() {
  FrameQueue queue(3);
  for (uint32_t i = 0; i < 5; i++) {
    Frame frame;
    frame.seq = i;
    queue.push(frame);
  }
  TEST_ASSERT_EQUAL_UINT16(3, queue.size());
  TEST_ASSERT_EQUAL_UINT32(2, queue.dropped());
  Frame out[3];
  TEST_ASSERT_EQUAL_UINT16(3, queue.peek(out, 3));
  TEST_ASSERT_EQUAL_UINT32(2, out[0].seq);
  queue.pop(2);
  TEST_ASSERT_EQUAL_UINT16(1, queue.size());
  TEST_ASSERT_EQUAL_UINT16(1, queue.peek(out, 3));
  TEST_ASSERT_EQUAL_UINT32(4, out[0].seq);
}

void test_backoff_schedule() {
  const uint16_t expected[] = {0, 1, 2, 4, 8, 15, 15, 15};
  for (uint16_t failures = 0; failures < 8; failures++) {
    TEST_ASSERT_EQUAL_UINT16(expected[failures], backoff_seconds(failures, 15));
  }
}

void test_perfusion_index() {
  uint32_t flat[4] = {1000, 1000, 1000, 1000};
  TEST_ASSERT_EQUAL_FLOAT(0.0f, perfusion_index(flat, 4));
  uint32_t wave[4] = {990, 1010, 990, 1010};
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 2.0f, perfusion_index(wave, 4));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_finger_hysteresis);
  RUN_TEST(test_median_needs_three_of_five);
  RUN_TEST(test_quality_score);
  RUN_TEST(test_queue_drops_the_oldest_when_full);
  RUN_TEST(test_backoff_schedule);
  RUN_TEST(test_perfusion_index);
  return UNITY_END();
}
