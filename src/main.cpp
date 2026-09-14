#include <Arduino.h>
#include "BluetoothSerial.h"
#include "esp_bt_device.h"

// Check that Bluetooth is enabled in the SDK configuration
#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please enable it in the SDK configuration.
#endif

// ==========================================
// Pinout Configuration (WEMOS LOLIN32 v1)
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

inline void setLed(bool state) {
  digitalWrite(LED_BUILTIN, state ? LED_ACTIVE_STATE : LED_INACTIVE_STATE);
}

// ==========================================
// Bluetooth Configuration
// ==========================================
const char* BT_DEVICE_NAME = "ESP32-RC-CAR";
BluetoothSerial SerialBT;

// Input buffers
String btBuffer = "";
String serialBuffer = "";

// ==========================================
// PWM & Failsafe Configuration
// ==========================================
const int PWM_FREQ = 20000;        // 20 kHz (inaudible)
const int PWM_RESOLUTION = 8;      // 8-bit resolution (0 - 255)
const int PWM_CH_LEFT = 0;
const int PWM_CH_RIGHT = 1;

const unsigned long FAILSAFE_TIMEOUT_MS = 600; // Stop motors if no command received for 600ms
unsigned long lastCommandTime = 0;
unsigned long lastStatusPrint = 0;

// ==========================================
// Motor Control Functions
// ==========================================

void setMotorLeft(bool forward, int speed) {
  if (INVERT_LEFT_MOTOR) forward = !forward;
  speed = constrain(speed, 0, 255);

  if (speed == 0) {
    digitalWrite(PIN_AIN1, LOW);
    digitalWrite(PIN_AIN2, LOW);
  } else if (forward) {
    digitalWrite(PIN_AIN1, HIGH);
    digitalWrite(PIN_AIN2, LOW);
  } else {
    digitalWrite(PIN_AIN1, LOW);
    digitalWrite(PIN_AIN2, HIGH);
  }
  ledcWrite(PWM_CH_LEFT, speed);
}

void setMotorRight(bool forward, int speed) {
  if (INVERT_RIGHT_MOTOR) forward = !forward;
  speed = constrain(speed, 0, 255);

  if (speed == 0) {
    digitalWrite(PIN_BIN1, LOW);
    digitalWrite(PIN_BIN2, LOW);
  } else if (forward) {
    digitalWrite(PIN_BIN1, HIGH);
    digitalWrite(PIN_BIN2, LOW);
  } else {
    digitalWrite(PIN_BIN1, LOW);
    digitalWrite(PIN_BIN2, HIGH);
  }
  ledcWrite(PWM_CH_RIGHT, speed);
}

void stopMotors() {
  setMotorLeft(true, 0);
  setMotorRight(true, 0);
}

/**
 * Drive the car using steer and throttle values.
 * @param steer: Steering value between -1.0 (turn left) and 1.0 (turn right)
 * @param throttle: Throttle value between -1.0 (reverse) and 1.0 (forward)
 */
void drive(float steer, float throttle) {
  if (INVERT_STEERING) {
    steer = -steer;
  }

  // Apply deadzone
  if (fabs(steer) < 0.05f) steer = 0.0f;
  if (fabs(throttle) < 0.05f) throttle = 0.0f;

  float left = 0.0f;
  float right = 0.0f;

  if (fabs(throttle) > 0.001f) {
    if (steer > 0.0f) {
      left = throttle;
      right = throttle * (1.0f - steer);
    } else if (steer < 0.0f) {
      left = throttle * (1.0f + steer);
      right = throttle;
    } else {
      left = throttle;
      right = throttle;
    }
  } else if (fabs(steer) > 0.001f) {
    float baseSpeed = 0.7f;
    if (steer > 0.0f) {
      left = baseSpeed;
      right = baseSpeed * (1.0f - steer);
    } else {
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
// Command Parser
// ==========================================

void processCommand(const String& cmd, const char* source) {
  String trimmed = cmd;
  trimmed.trim();
  if (trimmed.length() == 0) return;

  // Single-character test keys
  if (trimmed.equalsIgnoreCase("w")) {
    drive(0.0f, 1.0f);
    Serial.printf("[%s] CMD: Forward (w)\n", source);
    return;
  } else if (trimmed.equalsIgnoreCase("s")) {
    drive(0.0f, -1.0f);
    Serial.printf("[%s] CMD: Reverse (s)\n", source);
    return;
  } else if (trimmed.equalsIgnoreCase("a")) {
    drive(-0.6f, 0.8f);
    Serial.printf("[%s] CMD: Turn Left (a)\n", source);
    return;
  } else if (trimmed.equalsIgnoreCase("d")) {
    drive(0.6f, 0.8f);
    Serial.printf("[%s] CMD: Turn Right (d)\n", source);
    return;
  } else if (trimmed.equalsIgnoreCase("x") || trimmed.equalsIgnoreCase("stop")) {
    stopMotors();
    lastCommandTime = millis();
    Serial.printf("[%s] CMD: STOP (x)\n", source);
    return;
  }

  // CSV format: "<steer>,<throttle>"
  int commaIndex = trimmed.indexOf(',');
  if (commaIndex != -1) {
    float steer = trimmed.substring(0, commaIndex).toFloat();
    float throttle = trimmed.substring(commaIndex + 1).toFloat();

    if (fabs(steer) > 1.0f || fabs(throttle) > 1.0f) {
      float maxRange = (fabs(steer) > 100.0f || fabs(throttle) > 100.0f) ? 255.0f : 100.0f;
      steer /= maxRange;
      throttle /= maxRange;
    }

    drive(steer, throttle);
  }
}

void checkBluetoothInput() {
  while (SerialBT.available()) {
    char c = (char)SerialBT.read();
    if (c == '\n' || c == '\r') {
      if (btBuffer.length() > 0) {
        processCommand(btBuffer, "Bluetooth");
        btBuffer = "";
      }
    } else {
      btBuffer += c;
    }
  }
}

void checkSerialInput() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processCommand(serialBuffer, "Serial");
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
    }
  }
}

// ==========================================
// Setup & Main Loop
// ==========================================

void setup() {
  Serial.begin(115200);

  // Status LED
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

  // Initialize Bluetooth Serial (SPP)
  SerialBT.begin(BT_DEVICE_NAME);

  Serial.println("\n==========================================");
  Serial.println("  [OK] Bluetooth Serial (SPP) Started!");
  Serial.printf("  Device Name: %s\n", BT_DEVICE_NAME);

  const uint8_t* point = esp_bt_dev_get_address();
  if (point != NULL) {
    Serial.printf("  BT MAC:      %02X:%02X:%02X:%02X:%02X:%02X\n",
                  point[0], point[1], point[2], point[3], point[4], point[5]);
  }
  Serial.println("==========================================\n");

  Serial.println("Ready to receive drive commands over Bluetooth Serial & USB Serial.");
}

void loop() {
  // 1. Process incoming commands from Bluetooth and USB Serial
  checkBluetoothInput();
  checkSerialInput();

  unsigned long now = millis();

  // 2. Failsafe watchdog: Stop motors if command stream stops
  if (now - lastCommandTime > FAILSAFE_TIMEOUT_MS) {
    stopMotors();
    // Blink LED: Slow blink = Waiting for commands
    setLed((now / 500) % 2 == 0);

    // Print periodic status to Serial every 3 seconds while idle
    if (now - lastStatusPrint > 3000) {
      lastStatusPrint = now;
      bool btConnected = SerialBT.hasClient();
      Serial.printf("[IDLE] Waiting for commands... Bluetooth client connected: %s\n",
                    btConnected ? "YES" : "NO");
      if (!btConnected) {
        Serial.printf("       --> TIP: Pair with '%s' on your PC or run control.py --bt!\n",
                      BT_DEVICE_NAME);
      }
    }
  } else {
    // Solid LED when receiving active control stream
    setLed(true);
  }
}