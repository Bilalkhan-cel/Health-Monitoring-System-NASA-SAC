// Serial console (115200): status, scan, cal, ping, ip, server <url>, reboot, led.
#pragma once
#include <Arduino.h>

class NetClient;
class PulseSensor;
class TemperatureProbe;
class FrameQueue;

void cli_poll(NetClient &net, PulseSensor &pulse, TemperatureProbe &probe, FrameQueue &queue);
