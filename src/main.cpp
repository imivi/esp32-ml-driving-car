#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

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
// Wi-Fi Configuration
// ==========================================
#define USE_WIFI_AP true

// Access Point mode settings (when USE_WIFI_AP is true)
const char* AP_SSID = "ESP32-RC-CAR";
const char* AP_PASS = "12345678"; // Min 8 characters

// Station mode settings (when USE_WIFI_AP is false)
const char* STA_SSID = "YOUR_WIFI_SSID";
const char* STA_PASS = "YOUR_WIFI_PASSWORD";

// UDP Port for receiving driving commands
const unsigned int UDP_PORT = 4210;
WiFiUDP udp;
char udpPacketBuffer[256];

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

void checkUdpInput() {
  int packetSize = udp.parsePacket();
  if (packetSize > 0) {
    int len = udp.read(udpPacketBuffer, sizeof(udpPacketBuffer) - 1);
    if (len > 0) {
      udpPacketBuffer[len] = '\0';
      processCommand(String(udpPacketBuffer), "UDP");
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

  // Initialize Wi-Fi
  if (USE_WIFI_AP) {
    WiFi.disconnect(true);
    delay(100);
    WiFi.mode(WIFI_AP);
    bool apOk = WiFi.softAP(AP_SSID, AP_PASS);
    delay(200);

    Serial.println("\n==========================================");
    if (apOk) {
      Serial.println("  [OK] Wi-Fi Access Point Started!");
    } else {
      Serial.println("  [ERROR] Failed to start Access Point!");
    }
    Serial.printf("  SSID:        %s\n", AP_SSID);
    Serial.printf("  Password:    %s\n", AP_PASS);
    Serial.print("  ESP32 IP:    ");
    Serial.println(WiFi.softAPIP());
    Serial.printf("  UDP Port:    %u\n", UDP_PORT);
    Serial.println("==========================================\n");
  } else {
    WiFi.mode(WIFI_STA);
    WiFi.begin(STA_SSID, STA_PASS);
    Serial.print("\nConnecting to Wi-Fi: ");
    Serial.println(STA_SSID);
    unsigned long startAttemptTime = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 10000) {
      delay(300);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nConnected!");
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
    } else {
      Serial.println("\nFallback to Access Point mode...");
      WiFi.mode(WIFI_AP);
      WiFi.softAP(AP_SSID, AP_PASS);
    }
  }

  // Start UDP Listener
  udp.begin(UDP_PORT);

  Serial.println("Ready to receive drive commands over Wi-Fi UDP & USB Serial.");
}

void loop() {
  // 1. Process incoming commands
  checkUdpInput();
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
      if (USE_WIFI_AP) {
        int clients = WiFi.softAPgetStationNum();
        Serial.printf("[IDLE] Waiting for commands... Wi-Fi Clients connected: %d | AP IP: %s\n",
                      clients, WiFi.softAPIP().toString().c_str());
        if (clients == 0) {
          Serial.println("       --> TIP: Connect your PC to Wi-Fi 'ESP32-RC-CAR' (pwd: 12345678)!");
        }
      } else {
        Serial.printf("[IDLE] Waiting for commands... IP: %s\n", WiFi.localIP().toString().c_str());
      }
    }
  } else {
    // Solid LED when receiving active control stream
    setLed(true);
  }
}