# Esp32 RC car with sensors for machine learning

An end-to-end behavioral cloning (imitation learning) robotics platform. The car is remotely piloted via an Xbox controller while streaming sensor telemetry to a PC. The recorded telemetry trains a machine learning model to autonomously steer and navigate around a walled track.

---

## System Architecture

The robot delegates compute-heavy machine learning tasks to a host PC while maintaining low-latency motor control and sensor acquisition on the vehicle:

```
[Xbox Controller] (Manual Teleop)
       │
       ▼
[Host PC: Python] ──(Bluetooth / Wi-Fi UDP)──> [ESP32 Node] ──> [TB6612FNG] ──> [Motors]
       ▲                                               │
       └────────────────── Telemetry ──────────────────┘
                       (Left, Center, Right Distances)

```

1. **Hardware Layer (ESP32):** Reads three forward-facing distance sensors (Left, Center, Right) and generates hardware PWM via a TB6612FNG dual H-bridge motor driver.
2. **Telemetry & Wireless Bridge:** Streams distance readings to the host PC and receives drive commands over Bluetooth Serial (RFCOMM) or Wi-Fi UDP at ~30 Hz.
3. **Data Acquisition (`teleop_recorder.py`):** Captures synchronized time-series rows of `[dist_left, dist_center, dist_right]` mapped to target `[steer, throttle]` inputs from an Xbox controller.
4. **Model Training (`train.py`):** Trains an imitation learning regressor (Random Forest or Multi-Layer Perceptron) using `scikit-learn`.
5. **Autonomous Inference (`autonomous_pilot.py`):** Evaluates live sensor telemetry against the trained model in real-time, streaming predicted steering and throttle back to the vehicle with safety overrides.

---

## Hardware Bill of Materials

* **Microcontroller:** ESP32 WROOM DevKit v1
* **Motor Driver:** TB6612FNG Dual H-Bridge Driver
* **Sensors:** 3× Distance Sensors (VL53L0X Time-of-Flight LiDAR or HC-SR04 Ultrasonic)
* Left (~30°–45° offset)
* Center (0° forward)
* Right (~30°–45° offset)


* **Chassis & Actuation:** 2WD / 4WD robot chassis with DC gear motors
* **Power Source:**
* Independent motor power supply (e.g., 2S LiPo / 7.4V battery pack)
* 5V USB power bank or step-down buck converter for ESP32 logic


* **Host PC Controller:** Xbox Wireless Controller (USB or Bluetooth)

---

## Pinout Configuration

### ESP32 to TB6612FNG

| TB6612FNG Pin | ESP32 / Power Connection | Function |
| --- | --- | --- |
| **VM** | Motor Battery (+) [6V–12V] | Motor high-voltage rail |
| **VCC** | ESP32 **3V3** | Logic supply |
| **GND** | ESP32 **GND** & Battery (–) | **Common Ground** |
| **STBY** | GPIO 4 | Standby enable (`HIGH` = Active) |
| **PWMA** | GPIO 25 (LEDC Ch 0) | Motor A (Left) speed |
| **AIN1 / AIN2** | GPIO 26 / GPIO 27 | Motor A direction |
| **PWMB** | GPIO 14 (LEDC Ch 1) | Motor B (Right) speed |
| **BIN1 / BIN2** | GPIO 12 / GPIO 13 | Motor B direction |
| **AO1 / AO2** | Left Motor Terminals | Motor A outputs |
| **BO1 / BO2** | Right Motor Terminals | Motor B outputs |

---

## Software Pipeline & Workflow

### 1. Data Collection (Teleoperation)

Drive the car along the track while recording recovery maneuvers to avoid covariate shift:

```bash
python teleop_recorder.py

```

* Logs: `track_data.csv` (`dist_left`, `dist_center`, `dist_right`, `steer`, `throttle`).

### 2. Model Training

Train a regression model mapping the three distance features to steering and throttle targets:

```bash
python train.py

```

* Artifact: `pilot_model.pkl`

### 3. Autonomous Execution

Deploy the trained policy over the wireless serial link with emergency fail-safes:

```bash
python autonomous_pilot.py

```

* Includes a dead-man switch on the Xbox controller (`B` button) and emergency obstacle braking when `dist_center < 10 cm`.

---

## Flashing Firmware with PlatformIO

This project defines two separate firmware environments in `platformio.ini`:
* **`lolin32_car`**: Mounted on the RC car (WEMOS LOLIN32), controls TB6612FNG motor driver & receives commands via ESP-NOW.
* **`wroom_transmitter`**: Connected to the PC via USB (ESP32 WROOM DevKit), receives commands from Python scripts and broadcasts them via ESP-NOW.

### 1. Flash the Transmitter Dongle (`wroom_transmitter`)

**Via CLI:**
```bash
# Build and upload
pio run -e wroom_transmitter -t upload

# Upload and immediately open the serial monitor
pio run -e wroom_transmitter -t upload -t monitor
```

**Via VS Code GUI:**
1. Click the **PlatformIO** alien icon (👽) on the left sidebar.
2. Under **PROJECT TASKS**, expand **`wroom_transmitter`** -> **General**.
3. Click **Upload** (or **Upload and Monitor**).

> **Troubleshooting: "Wrong boot mode detected (0x13) / Failed to connect to ESP32"**
> If the upload fails or hangs at `Connecting........_____.....`:
> 1. Run the upload command.
> 2. As soon as `Connecting........` appears, press and **HOLD the `BOOT` (IO0) button** on the ESP32 board.
> 3. Release the button once `Writing at 0x00001000...` begins.
> *(Alternative: Hold `BOOT`, press and release `EN`/`RST`, then release `BOOT`).*

---

### 2. Flash the Car Receiver (`lolin32_car`)

**Via CLI:**
```bash
pio run -e lolin32_car -t upload -t monitor
```

**Via VS Code GUI:**
1. Under **PROJECT TASKS**, expand **`lolin32_car`** -> **General**.
2. Click **Upload and Monitor**.
3. Note down the printed **Receiver MAC Address** on startup to verify it matches `broadcastAddress` in `src/transmitter_dongle.cpp`.
