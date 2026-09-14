#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "espnow_protocol.h"

// ==========================================
// ESP-NOW Receiver Car (WEMOS LOLIN32 v1)
// Mounted on the RC car chassis
// Receives ControlPacket via ESP-NOW and
// drives the TB6612FNG dual motor driver.
// ==========================================

#define PIN_STBY 4

// Motor A (Left)
#define PIN_PWMA 25
#define PIN_AIN1 26
#define PIN_AIN2 27

// Motor B (Right)
#define PIN_PWMB 14
#define PIN_BIN1 12
#define PIN_BIN2 13

// LOLIN32 Built-in LED (GPIO 5, Active LOW)
#ifndef LED_BUILTIN
#define LED_BUILTIN 5
#endif

// Motor direction invert flags (set to true if your motor wiring is physically inverted)
const bool INVERT_LEFT_MOTOR = false;
const bool INVERT_RIGHT_MOTOR = false;
const bool INVERT_STEERING = true; // Inverts Left / Right steering direction

// LED Logic polarity (Active LOW for LOLIN32)
#define LED_ACTIVE_STATE LOW
#define LED_INACTIVE_STATE HIGH

inline void setLed(bool state)
{
  digitalWrite(LED_BUILTIN, state ? LED_ACTIVE_STATE : LED_INACTIVE_STATE);
}

// ==========================================
// PWM & Failsafe Configuration
// ==========================================
const int PWM_FREQ = 20000;   // 20 kHz (inaudible)
const int PWM_RESOLUTION = 8; // 8-bit resolution (0 - 255)
const int PWM_CH_LEFT = 0;
const int PWM_CH_RIGHT = 1;

const unsigned long FAILSAFE_TIMEOUT_MS = 600; // Stop motors if no command received for 600ms
volatile unsigned long lastCommandTime = 0;
unsigned long lastStatusPrint = 0;
volatile uint32_t lastReceivedSeq = 0;
volatile uint32_t packetCount = 0;

// USB Serial input buffer for tethered debugging
String serialBuffer = "";

// ==========================================
// Motor Control Functions
// ==========================================

void setMotorLeft(bool forward, int speed)
{
  if (INVERT_LEFT_MOTOR)
    forward = !forward;
  speed = constrain(speed, 0, 255);

  if (speed == 0)
  {
    digitalWrite(PIN_AIN1, LOW);
    digitalWrite(PIN_AIN2, LOW);
  }
  else if (forward)
  {
    digitalWrite(PIN_AIN1, HIGH);
    digitalWrite(PIN_AIN2, LOW);
  }
  else
  {
    digitalWrite(PIN_AIN1, LOW);
    digitalWrite(PIN_AIN2, HIGH);
  }
  ledcWrite(PWM_CH_LEFT, speed);
}

void setMotorRight(bool forward, int speed)
{
  if (INVERT_RIGHT_MOTOR)
    forward = !forward;
  speed = constrain(speed, 0, 255);

  if (speed == 0)
  {
    digitalWrite(PIN_BIN1, LOW);
    digitalWrite(PIN_BIN2, LOW);
  }
  else if (forward)
  {
    digitalWrite(PIN_BIN1, HIGH);
    digitalWrite(PIN_BIN2, LOW);
  }
  else
  {
    digitalWrite(PIN_BIN1, LOW);
    digitalWrite(PIN_BIN2, HIGH);
  }
  ledcWrite(PWM_CH_RIGHT, speed);
}

void stopMotors()
{
  setMotorLeft(true, 0);
  setMotorRight(true, 0);
}

/**
 * Drive the car using steer and throttle values.
 * @param steer: Steering value between -1.0 (turn left) and 1.0 (turn right)
 * @param throttle: Throttle value between -1.0 (reverse) and 1.0 (forward)
 */
void drive(float steer, float throttle)
{
  if (INVERT_STEERING)
  {
    steer = -steer;
  }

  // Apply deadzone
  if (fabs(steer) < 0.05f)
    steer = 0.0f;
  if (fabs(throttle) < 0.05f)
    throttle = 0.0f;

  float left = 0.0f;
  float right = 0.0f;

  if (fabs(throttle) > 0.001f)
  {
    if (steer > 0.0f)
    {
      left = throttle;
      right = throttle * (1.0f - steer);
    }
    else if (steer < 0.0f)
    {
      left = throttle * (1.0f + steer);
      right = throttle;
    }
    else
    {
      left = throttle;
      right = throttle;
    }
  }
  else if (fabs(steer) > 0.001f)
  {
    float baseSpeed = 0.7f;
    if (steer > 0.0f)
    {
      left = baseSpeed;
      right = baseSpeed * (1.0f - steer);
    }
    else
    {
      left = baseSpeed * (1.0f + steer);
      right = baseSpeed;
    }
  }

  // Clamp within [-1.0, 1.0]
  left = constrain(left, -1.0f, 1.0f);
  right = constrain(right, -1.0f, 1.0f);

  int leftSpeed = (int)(fabs(left) * 255.0f);
  int rightSpeed = (int)(fabs(right) * 255.0f);

  setMotorLeft(left >= 0, leftSpeed);
  setMotorRight(right >= 0, rightSpeed);

  lastCommandTime = millis();
}

// ==========================================
// ESP-NOW Receive Callback
// ==========================================
void onDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len)
{
  if (len == sizeof(ControlPacket))
  {
    ControlPacket packet;
    memcpy(&packet, incomingData, sizeof(ControlPacket));
    lastReceivedSeq = packet.seq;
    packetCount++;
    drive(packet.steer, packet.throttle);
  }
}

// ==========================================
// Optional Direct USB Serial Parser (Debugging)
// ==========================================
void checkSerialInput()
{
  while (Serial.available())
  {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r')
    {
      if (serialBuffer.length() > 0)
      {
        String trimmed = serialBuffer;
        trimmed.trim();
        serialBuffer = "";
        if (trimmed.equalsIgnoreCase("x") || trimmed.equalsIgnoreCase("stop"))
        {
          stopMotors();
          lastCommandTime = millis();
        }
        else
        {
          int commaIndex = trimmed.indexOf(',');
          if (commaIndex != -1)
          {
            float s = trimmed.substring(0, commaIndex).toFloat();
            float t = trimmed.substring(commaIndex + 1).toFloat();
            drive(s, t);
          }
        }
      }
    }
    else
    {
      serialBuffer += c;
    }
  }
}

void setup()
{
  Serial.begin(115200);

  pinMode(LED_BUILTIN, OUTPUT);
  setLed(true);

  // Motor Direction Pins
  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT);
  pinMode(PIN_BIN2, OUTPUT);

  // Standby Pin
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, HIGH);

  // Configure LEDC PWM for Motor Speed
  ledcSetup(PWM_CH_LEFT, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(PIN_PWMA, PWM_CH_LEFT);

  ledcSetup(PWM_CH_RIGHT, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(PIN_PWMB, PWM_CH_RIGHT);

  stopMotors();

  // Set device as a Wi-Fi Station for ESP-NOW
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  // Force Wi-Fi to Channel 1 (must match transmitter)
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  Serial.println("\n==========================================");
  Serial.println("  ESP-NOW Receiver (RC Car - LOLIN32)");
  Serial.print("  Receiver MAC:  ");
  Serial.println(WiFi.macAddress());
  Serial.print("  Wi-Fi Channel: ");
  Serial.println(WiFi.channel());

  // Initialize ESP-NOW
  if (esp_now_init() != ESP_OK)
  {
    Serial.println("  [ERROR] Error initializing ESP-NOW!");
    return;
  }
  Serial.println("  [OK] ESP-NOW Initialized Successfully");

  esp_now_register_recv_cb(onDataRecv);

  Serial.println("==========================================\n");
  Serial.println("Ready to receive driving commands wirelessly via ESP-NOW.");
}

void loop()
{
  checkSerialInput();

  unsigned long now = millis();

  // Failsafe watchdog: Stop motors if command stream stops
  if (now - lastCommandTime > FAILSAFE_TIMEOUT_MS)
  {
    stopMotors();
    // Blink LED: Slow blink = Waiting for commands
    setLed((now / 500) % 2 == 0);

    // Periodic heartbeat to serial
    if (now - lastStatusPrint > 3000)
    {
      lastStatusPrint = now;
      Serial.printf("[CAR IDLE] Waiting for ESP-NOW commands... Packets received: %u\n", packetCount);
    }
  }
  else
  {
    // Solid LED when receiving active control stream
    setLed(true);
  }
}
