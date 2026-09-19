# ESP32 Machine Learning Autonomous RC Car

An end-to-end behavioral cloning (imitation learning) robotics platform. The car is remotely piloted via an Xbox controller while streaming real-time Time-of-Flight LiDAR telemetry to a PC. The recorded telemetry trains an ensemble Random Forest classifier to autonomously navigate and steer around a walled track without human intervention.

---

## System Architecture

The vehicle delegates compute-heavy machine learning inference to a host PC while maintaining low-latency wireless communication, sensor acquisition, and motor control via **ESP-NOW**:

```
[Xbox Controller] (Teleoperation / Safety Override)
       │
       ▼
[Host PC: Python] (manual_control.py / autopilot.py)
       │ ▲
  (USB Serial @ 115200 baud)
       ▼ │
[ESP32 WROOM Transmitter Dongle]
       │ ▲
  (Wireless ESP-NOW Protocol @ ~30–50 Hz)
       ▼ │
[ESP32 LOLIN32 Car Receiver] ──> [TB6612FNG Driver] ──> [DC Gear Motors]
       ▲
       └── [3× VL53L0X ToF LiDAR Sensors] (Left, Center, Right)
```

1. **Car Node (WEMOS LOLIN32 v1):** Reads 3× forward-facing VL53L0X Time-of-Flight distance sensors over I2C, transmits telemetry packets via ESP-NOW, and generates hardware PWM motor signals via a TB6612FNG dual H-bridge.
2. **Transmitter Dongle (ESP32 WROOM DevKit v1):** Plugs into the PC via USB. Acts as a bi-directional wireless bridge, forwarding serial driving commands to the car and streaming sensor telemetry back to Python.
3. **Data Acquisition (`manual_control.py`):** Captures synchronized time-series rows of distance sensor telemetry `[dist_left_mm, dist_center_mm, dist_right_mm]` mapped to driving directions (`FORWARD`, `FORWARD_LEFT`, `FORWARD_RIGHT`) when holding `[A]` on the Xbox controller.
4. **Model Training (`train.py`):** Trains a Random Forest classifier using `scikit-learn` on sensor distances and exports the production model artifact to `pilot_model.pkl`.
5. **Autonomous Inference (`autopilot.py`):** Evaluates live incoming sensor telemetry against the trained model in real time (~30 Hz), streaming predicted steering and throttle actuation back to the vehicle with collision braking and manual safety overrides.

---

## Hardware Bill of Materials

* **Microcontrollers:**
  * **Car Receiver:** WEMOS LOLIN32 v1 (ESP32-WROOM-32)
  * **Transmitter Dongle:** ESP32 WROOM DevKit v1
* **Motor Driver:** TB6612FNG Dual H-Bridge Driver
* **Sensors:** 3× VL53L0X Time-of-Flight (ToF) Laser Distance Sensors
  * **Left:** ~35°–45° angled outward
  * **Center:** 0° facing forward
  * **Right:** ~35°–45° angled outward
* **Chassis & Motors:** 2WD / 4WD robot chassis with DC gear motors
* **Power Supplies:**
  * **Motors:** Independent battery pack (e.g., 2S LiPo / 7.4V) connected to TB6612FNG `VM`
  * **Car Logic:** 5V power bank or 3.7V LiPo connected to LOLIN32
* **Host PC Controller:** Xbox Wireless / Wired Controller (USB or Bluetooth)

---

## Hardware Pinout Configuration

> **Visual Schematic:** See the complete scalable wiring diagram at [docs/wiring_diagram.svg](docs/wiring_diagram.svg).

### 1. TB6612FNG Motor Driver $\rightarrow$ LOLIN32 v1

| TB6612FNG Pin | LOLIN32 v1 Pin | Power / Motor | Description |
| :--- | :--- | :--- | :--- |
| **VM** | — | Battery **(+)** (6V–12V) | Motor power rail |
| **VCC** | **3V** (3.3V) | — | Driver logic supply |
| **GND** | **GND** | Battery **(–)** | **Common Ground** (ESP32 GND tied to battery negative) |
| **STBY** | **GPIO 4** | — | Standby enable (`HIGH` = Active) |
| **PWMA** | **GPIO 25** | — | Motor A (Left) speed (LEDC Ch 0 PWM) |
| **AIN1 / AIN2**| **GPIO 26 / 27** | — | Motor A direction |
| **PWMB** | **GPIO 14** | — | Motor B (Right) speed (LEDC Ch 1 PWM) |
| **BIN1 / BIN2**| **GPIO 12 / 13** | — | Motor B direction |
| **AO1 / AO2** | — | Left Motor | Motor A terminals |
| **BO1 / BO2** | — | Right Motor | Motor B terminals |

---

### 2. 3× VL53L0X ToF Distance Sensors $\rightarrow$ LOLIN32 v1

All three sensors share the hardware I2C bus (`SDA` / `SCL`). During boot, the LOLIN32 uses their individual `XSHUT` pins to dynamically assign unique I2C addresses:

| Sensor | I2C Address | LOLIN32 `XSHUT` Pin | Shared I2C Pins |
| :--- | :--- | :--- | :--- |
| **Left Sensor** | `0x30` | **GPIO 18** | **SDA:** GPIO 21<br>**SCL:** GPIO 22<br>**VIN:** 3.3V<br>**GND:** GND |
| **Center Sensor** | `0x31` | **GPIO 19** | |
| **Right Sensor** | `0x32` | **GPIO 23** | |

---

## Software Pipeline & Workflow

### 1. Data Collection (Teleoperation)

Plug the transmitter dongle into your PC and connect your Xbox controller:

```bash
uv run manual_control.py
```

* **Controls:**
  * **Left Stick X:** Steering (`-1.0` full left to `+1.0` full right)
  * **Left Stick Y / Triggers:** Throttle (`RT` forward, `LT` reverse)
  * **`B` Button:** Emergency Brake / Instant Stop
  * **Hold `[A]` Button:** Continuously record distance telemetry & direction labels at 20 Hz
* **Output File:** `track_data.csv` (`timestamp_iso`, `timestamp_epoch`, `dist_left_mm`, `dist_center_mm`, `dist_right_mm`, `steer`, `throttle`, `direction`).

---

### 2. Machine Learning Training

Train an ensemble Random Forest classifier on the 3 distance sensor inputs (`dist_left_mm`, `dist_center_mm`, `dist_right_mm`):

```bash
uv run python train.py
```

* **Features:** Pure distance sensor inputs (timestamps, steer, and throttle are excluded from training features).
* **Target Classes:** `FORWARD`, `FORWARD_LEFT`, `FORWARD_RIGHT`
* **Validation:** 5-fold stratified cross-validation and held-out test evaluation (~82–85% test accuracy).
* **Model Artifact:** Exported to **`pilot_model.pkl`**.

---

### 3. Autonomous Driving (Inference)

Deploy the trained model to drive the vehicle autonomously around the track:

```bash
uv run python autopilot.py
```

* **Real-Time Evaluation:** Evaluates live sensor telemetry at 30 Hz against `pilot_model.pkl` to select optimal driving direction.
* **Actuation Mapping:**
  * `FORWARD`: Straight cruise (`steer: 0.00`, `throttle: 0.85`)
  * `FORWARD_LEFT`: Arcing left turn (`steer: -0.55`, `throttle: 0.77`)
  * `FORWARD_RIGHT`: Arcing right turn (`steer: +0.55`, `throttle: 0.77`)
* **Safety Overrides:**
  * **Emergency Obstacle Braking:** If `dist_center_mm < 140 mm`, immediately halts motors to prevent wall crashes.
  * **Dead-Man Switch:** Pressing **`B`** on the Xbox controller instantly engages emergency brake.
  * **Manual Joystick Takeover:** Moving the left stick instantly overrides the autonomous policy.
  * **Stale Telemetry Failsafe:** Stops vehicle if telemetry stream pauses for > 1.0 s.

#### Offline Simulation Mode
Verify model predictions against recorded track data without connecting to the car:

```bash
uv run python autopilot.py --simulate
```

---

## Flashing Firmware with PlatformIO

This project defines two separate firmware environments in [`platformio.ini`](platformio.ini):

### 1. Transmitter Dongle (`wroom_transmitter`)
Connected to the PC via USB, receives serial commands from Python and broadcasts via ESP-NOW:

```bash
pio run -e wroom_transmitter -t upload -t monitor
```

> **Troubleshooting: "Connecting........_____....."**
> If upload hangs while connecting:
> 1. Run the upload command.
> 2. When `Connecting........` appears, press and **HOLD the `BOOT` button** on the ESP32 board.
> 3. Release once writing begins.

### 2. Car Receiver (`lolin32_car`)
Mounted on the chassis, interfaces with TB6612FNG and 3× VL53L0X ToF sensors:

```bash
pio run -e lolin32_car -t upload -t monitor
```
