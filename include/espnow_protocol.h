#pragma once
#include <Arduino.h>

// ESP-NOW Data Packet structure shared between transmitter and receiver
typedef struct __attribute__((packed))
{
  float steer;    // -1.0 (Left) to +1.0 (Right)
  float throttle; // -1.0 (Reverse) to +1.0 (Forward)
  uint32_t seq;   // Sequence counter for packet tracking
} ControlPacket;

// Telemetry Packet structure sent from RC car back to transmitter dongle
typedef struct __attribute__((packed))
{
  uint16_t dist_left;   // Distance in mm (8190 = out of range / error)
  uint16_t dist_center; // Distance in mm
  uint16_t dist_right;  // Distance in mm
  uint32_t seq;         // Packet sequence counter
} TelemetryPacket;
