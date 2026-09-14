#pragma once
#include <Arduino.h>

// ESP-NOW Data Packet structure shared between transmitter and receiver
typedef struct __attribute__((packed)) {
  float steer;     // -1.0 (Left) to +1.0 (Right)
  float throttle;  // -1.0 (Reverse) to +1.0 (Forward)
  uint32_t seq;    // Sequence counter for packet tracking
} ControlPacket;

