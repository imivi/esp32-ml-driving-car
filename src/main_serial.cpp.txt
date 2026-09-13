#include <Arduino.h>

// ==========================================
// Pinout Configuration (WEMOS LOLIN32 v1)
// ==========================================
// TB6612FNG Standby pin
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

// LED Logic polarity (Active LOW for LOLIN32)
#define LED_ACTIVE_STATE LOW
#define LED_INACTIVE_STATE HIGH

inline void setLed(bool state) {
  digitalWrite(LED_BUILTIN, state ? LED_ACTIVE_STATE : LED_INACTIVE_STATE);
}

// ==========================================
// PWM & Failsafe Configuration
// ==========================================
const int PWM_FREQ = 20000;        // 20 kHz (inaudible to avoid motor whine)
const int PWM_RESOLUTION = 8;      // 8-bit resolution (0 - 255)
const int PWM_CH_LEFT = 0;         // LEDC Channel 0
const int PWM_CH_RIGHT = 1;        // LEDC Channel 1

const unsigned long FAILSAFE_TIMEOUT_MS = 500; // Stop motors if no command received for 500ms
unsigned long lastCommandTime = 0;

// Serial input buffer
String serialBuffer = "";

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
 * Uses forward-biased differential steering so turning slows the inside wheel
 * instead of reversing it, creating smooth forward arcing turns rather than spinning in place.
 *
 * @param steer: Steering value between -1.0 (turn left) and 1.0 (turn right)
 * @param throttle: Throttle value between -1.0 (reverse) and 1.0 (forward)
 */
void drive(float steer, float throttle) {
  // Apply deadzone
  if (fabs(steer) < 0.05f) steer = 0.0f;
  if (fabs(throttle) < 0.05f) throttle = 0.0f;

  float left = 0.0f;
  float right = 0.0f;

  if (fabs(throttle) > 0.001f) {
    // When driving forward or backward, scale the inside wheel down smoothly
    if (steer > 0.0f) {
      // Turn Right: Left wheel at full throttle, Right wheel slowed down
      left = throttle;
      right = throttle * (1.0f - steer);
    } else if (steer < 0.0f) {
      // Turn Left: Left wheel slowed down, Right wheel at full throttle
      left = throttle * (1.0f + steer); // (1.0 + negative steer) reduces speed
      right = throttle;
    } else {
      // Straight
      left = throttle;
      right = throttle;
    }
  } else if (fabs(steer) > 0.001f) {
    // If steering is pressed alone (throttle is 0), move forward while curving
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

  // Convert to PWM 0-255
  int leftSpeed = (int)(fabs(left) * 255.0f);
  int rightSpeed = (int)(fabs(right) * 255.0f);

  setMotorLeft(left >= 0, leftSpeed);
  setMotorRight(right >= 0, rightSpeed);

  lastCommandTime = millis();
}

// ==========================================
// Command Parser
// ==========================================

void processCommand(const String& cmd) {
  String trimmed = cmd;
  trimmed.trim();
  if (trimmed.length() == 0) return;

  // 1. Single-character manual testing commands
  if (trimmed.equalsIgnoreCase("w")) {
    drive(0.0f, 1.0f);    // Full Forward
    return;
  } else if (trimmed.equalsIgnoreCase("s")) {
    drive(0.0f, -1.0f);   // Full Reverse
    return;
  } else if (trimmed.equalsIgnoreCase("a")) {
    drive(-0.6f, 0.8f);   // Curve Left forward (Left: 32% speed, Right: 80% speed)
    return;
  } else if (trimmed.equalsIgnoreCase("d")) {
    drive(0.6f, 0.8f);    // Curve Right forward (Left: 80% speed, Right: 32% speed)
    return;
  } else if (trimmed.equalsIgnoreCase("x") || trimmed.equalsIgnoreCase("stop")) {
    stopMotors();
    lastCommandTime = millis();
    return;
  }

  // 2. CSV format: "<steer>,<throttle>" (e.g., "-0.25,0.8" or "0,255")
  int commaIndex = trimmed.indexOf(',');
  if (commaIndex != -1) {
    float steer = trimmed.substring(0, commaIndex).toFloat();
    float throttle = trimmed.substring(commaIndex + 1).toFloat();

    // Support both normalized range [-1.0, 1.0] and raw range [-255, 255] or [-100, 100]
    if (fabs(steer) > 1.0f || fabs(throttle) > 1.0f) {
      // Normalize if given in -100..100 or -255..255
      float maxRange = (fabs(steer) > 100.0f || fabs(throttle) > 100.0f) ? 255.0f : 100.0f;
      steer /= maxRange;
      throttle /= maxRange;
    }

    drive(steer, throttle);
  }
}

void checkSerialInput() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processCommand(serialBuffer);
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
  setLed(true); // Turn ON LED at startup

  // Motor Direction Pins
  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT);
  pinMode(PIN_BIN2, OUTPUT);

  // Standby Pin
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, HIGH); // Enable TB6612FNG driver

  // Configure LEDC PWM for Motor Speed
  ledcSetup(PWM_CH_LEFT, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(PIN_PWMA, PWM_CH_LEFT);

  ledcSetup(PWM_CH_RIGHT, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(PIN_PWMB, PWM_CH_RIGHT);

  // Initialize motors to stopped state
  stopMotors();

  Serial.println("WEMOS LOLIN32 v1 Motor Controller Ready.");
  Serial.println("Commands: CSV '<steer>,<throttle>' (-1.0 to 1.0) or keys W/A/S/D/X");
}

void loop() {
  // Read incoming drive commands from USB Serial
  checkSerialInput();

  // Failsafe watchdog: Stop motors if command stream stops
  if (millis() - lastCommandTime > FAILSAFE_TIMEOUT_MS) {
    stopMotors();
    // Blink LED slowly to indicate idle/waiting state
    setLed((millis() / 500) % 2 == 0);
  } else {
    // Keep LED solid ON when receiving active commands
    setLed(true);
  }
}