// Every GPIO assignment lives here and only here (Section 10A.2). Check your board's
// silkscreen first: pins labelled 21, 22 and 4 must exist. Avoid GPIO 6-11 (flash),
// 34-39 (input only, cannot drive 1-Wire) and the strapping pins 0/2/5/12/15 for sensors.
#pragma once

#define PIN_I2C_SDA 21   // specified by the owner
#define PIN_I2C_SCL 22   // specified by the owner
#define PIN_ONEWIRE 4    // proposed by the design; any free output-capable pin works

// Optional status LED. Many DevKit boards have one on GPIO 2, some have none: this is
// "needs physical test" in docs/HARDWARE_FACTS.md. Every LED pattern is mirrored to serial.
#define PIN_STATUS_LED 2
#define STATUS_LED_ENABLED 1
