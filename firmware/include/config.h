// Committed defaults for the AstroVital wearable. Secrets live in secrets.h (git-ignored).
#pragma once

#define FW_VERSION "1.0.0"
#define SERIAL_BAUD 115200

// MAX30102 setup: LED 60, average 4, red+IR, 100 Hz, 411 us, range 4096
// -> an effective 25 samples/s, matching the Maxim algorithm's assumption.
#define MAX_LED_BRIGHTNESS 60
#define MAX_SAMPLE_AVERAGE 4
#define MAX_LED_MODE 2
#define MAX_SAMPLE_RATE 100
#define MAX_PULSE_WIDTH 411
#define MAX_ADC_RANGE 4096
#define I2C_HZ 400000

#define SAMPLES_PER_FRAME 25      // one frame per second
#define WINDOW_SAMPLES 100        // 4 s buffers for the algorithm
#define FINGER_ON_IR 50000        // tune with the serial `cal` command (Appendix G, T5b)
#define FINGER_OFF_IR 30000
#define SETTLE_S 2                // after the first full window, wait this long before reporting
#define SATURATION_IR 260000
#define HR_MIN 30
#define HR_MAX 220
#define SPO2_MIN 70
#define SPO2_MAX 100
#define SEND_PPG 1                // send the 25-point pulse wave with each frame

// Temperature (raw probe reading only; offsets live on the server).
#define TEMP_RESOLUTION_BITS 12
#define TEMP_READ_DELAY_MS 800
#define TEMP_MIN_C 10.0f
#define TEMP_MAX_C 50.0f

// Network
#define SEND_INTERVAL_MS 1000
#define MAX_BATCH 20
#define BUFFER_MAX 300            // 5 minutes of frames in RAM
#define HTTP_TIMEOUT_MS 3000
#define BACKOFF_CAP_S 15
#define REDISCOVER_AFTER_MS 60000
#define WIFI_FORCE_RECONNECT_MS 20000
#define WIFI_RESTART_MS 300000
#define I2C_ERROR_LIMIT 3
#define HEAP_REPORT_MS 60000
#define PING_FAILS_BEFORE_MDNS 3
