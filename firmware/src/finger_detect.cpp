#include "finger_detect.h"

bool FingerDetector::update(uint32_t mean_ir) {
  if (!on_ && mean_ir > on_level_) {
    on_ = true;
  } else if (on_ && mean_ir < off_level_) {
    on_ = false;
  }
  return on_;
}
