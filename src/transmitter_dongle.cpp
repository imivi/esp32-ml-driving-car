#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "espnow_protocol.h"

// ==========================================
// ESP-NOW Transmitter Dongle (ESP32 WROOM)
// Plugged into the PC via USB Serial
// Reads commands (<steer>,<throttle>) from control.py
// and broadcasts them via ESP-NOW to the RC car.
// ==========================================

#ifndef LED_BUILTIN
#define LED_BUILTIN 2 // GPIO 2 on standard ESP32 WROOM DevKit
#endif

// Broadcast address: sends packet to ANY listening ESP-NOW receiver without pairing MAC addresses
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

ControlPacket txPacket;
uint32_t packetSequence = 0;
String serialBuffer = "";

// Track send status
volatile bool lastSendSuccess = false;
unsigned long lastSerialCmdTime = 0;
unsigned long lastStatusPrint = 0;

void onDataSent(const uint8_t *mac_addr, esp_now_send_status_t status)
{
  lastSendSuccess = (status == ESP_NOW_SEND_SUCCESS);
}

void onDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len)
{
  if (len == sizeof(TelemetryPacket))
  {
    TelemetryPacket pkt;
    memcpy(&pkt, incomingData, sizeof(TelemetryPacket));
    // Print telemetry to USB Serial in easily parseable CSV format: TELEM:<left>,<center>,<right>,<seq>
    Serial.printf("TELEM:%u,%u,%u,%u\n", pkt.dist_left, pkt.dist_center, pkt.dist_right, pkt.seq);
  }
}

void parseAndTransmit(const String &cmd)
{
  String trimmed = cmd;
  trimmed.trim();
  if (trimmed.length() == 0)
    return;

  float steer = 0.0f;
  float throttle = 0.0f;
  bool valid = false;

  // Single-key commands
  if (trimmed.equalsIgnoreCase("w"))
  {
    steer = 0.0f;
    throttle = 1.0f;
    valid = true;
  }
  else if (trimmed.equalsIgnoreCase("s"))
  {
    steer = 0.0f;
    throttle = -1.0f;
    valid = true;
  }
  else if (trimmed.equalsIgnoreCase("a"))
  {
    steer = -0.6f;
    throttle = 0.8f;
    valid = true;
  }
  else if (trimmed.equalsIgnoreCase("d"))
  {
    steer = 0.6f;
    throttle = 0.8f;
    valid = true;
  }
  else if (trimmed.equalsIgnoreCase("x") || trimmed.equalsIgnoreCase("stop"))
  {
    steer = 0.0f;
    throttle = 0.0f;
    valid = true;
  }
  else
  {
    // CSV format: "<steer>,<throttle>"
    int commaIndex = trimmed.indexOf(',');
    if (commaIndex != -1)
    {
      steer = trimmed.substring(0, commaIndex).toFloat();
      throttle = trimmed.substring(commaIndex + 1).toFloat();

      if (fabs(steer) > 1.0f || fabs(throttle) > 1.0f)
      {
        float maxRange = (fabs(steer) > 100.0f || fabs(throttle) > 100.0f) ? 255.0f : 100.0f;
        steer /= maxRange;
        throttle /= maxRange;
      }
      valid = true;
    }
  }

  if (valid)
  {
    txPacket.steer = constrain(steer, -1.0f, 1.0f);
    txPacket.throttle = constrain(throttle, -1.0f, 1.0f);
    txPacket.seq = ++packetSequence;

    esp_now_send(broadcastAddress, (uint8_t *)&txPacket, sizeof(ControlPacket));
    lastSerialCmdTime = millis();
    digitalWrite(LED_BUILTIN, HIGH);
  }
}

void setup()
{
  Serial.begin(115200);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Set device as a Wi-Fi Station for ESP-NOW (no router connection required)
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  // Force Wi-Fi to Channel 1
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  Serial.println("\n==========================================");
  Serial.println("  ESP-NOW Transmitter (PC USB Dongle)");
  Serial.print("  Transmitter MAC: ");
  Serial.println(WiFi.macAddress());
  Serial.print("  Wi-Fi Channel:   ");
  Serial.println(WiFi.channel());

  // Initialize ESP-NOW
  if (esp_now_init() != ESP_OK)
  {
    Serial.println("  [ERROR] Error initializing ESP-NOW!");
    return;
  }
  Serial.println("  [OK] ESP-NOW Initialized Successfully");

  esp_now_register_send_cb(onDataSent);
  esp_now_register_recv_cb(onDataRecv);

  // Register peer
  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 1; // Locked to channel 1
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK)
  {
    Serial.println("  [ERROR] Failed to add peer");
    return;
  }
  Serial.printf("  [OK] Peer Added (%02X:%02X:%02X:%02X:%02X:%02X) on Ch 1\n",
                broadcastAddress[0], broadcastAddress[1], broadcastAddress[2],
                broadcastAddress[3], broadcastAddress[4], broadcastAddress[5]);
  Serial.println("==========================================\n");
  Serial.println("Ready to receive USB Serial commands from control.py and forward via ESP-NOW.");
}

void loop()
{
  // Read Serial inputs from PC
  while (Serial.available())
  {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r')
    {
      if (serialBuffer.length() > 0)
      {
        parseAndTransmit(serialBuffer);
        serialBuffer = "";
      }
    }
    else
    {
      serialBuffer += c;
    }
  }

  unsigned long now = millis();

  // Turn off LED 50ms after sending command
  if (now - lastSerialCmdTime > 50)
  {
    digitalWrite(LED_BUILTIN, LOW);
  }

  // Periodic heartbeat message if idle
  if (now - lastStatusPrint > 3000)
  {
    lastStatusPrint = now;
    if (now - lastSerialCmdTime > 1000)
    {
      Serial.printf("[TRANSMITTER IDLE] Waiting for USB commands from PC (control.py). Total sent: %u\n", packetSequence);
    }
  }
}
