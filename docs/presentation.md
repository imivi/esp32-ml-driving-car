---
marp: true
theme: default
paginate: true
size: 16:9
transition: slide
style: |
  section {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
    font-size: 19px;
    padding: 30px 50px;
    background-color: #f8fafc;
    color: #1e293b;
    line-height: 1.45;
  }
  h1 {
    color: #1e3a8a;
    font-size: 38px;
    margin-bottom: 8px;
  }
  h2 {
    color: #1e40af;
    font-size: 26px;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 6px;
    margin-top: 0;
    margin-bottom: 16px;
  }
  h3 {
    color: #2563eb;
    font-size: 19px;
    margin-top: 0;
    margin-bottom: 6px;
  }
  strong {
    color: #0f172a;
  }
  ul {
    margin-top: 4px;
    margin-bottom: 8px;
    line-height: 1.45;
    padding-left: 24px;
  }
  li {
    margin-bottom: 6px;
  }
  .tag {
    display: inline-block;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    color: #1d4ed8;
    padding: 2px 10px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 700;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: 1.15fr 0.85fr;
    gap: 24px;
    align-items: start;
  }
  .grid-2-equal {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    align-items: start;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
  }
  .card {
    background: #ffffff;
    border: 1.5px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.04);
  }
  .card:last-child {
    margin-bottom: 0;
  }
  .card > *:first-child {
    margin-top: 0;
  }
  .card > *:last-child {
    margin-bottom: 0;
  }
  .highlight-card {
    background: #f0fdf4;
    border: 1.5px solid #86efac;
    border-radius: 10px;
    padding: 14px 18px;
    margin-top: 14px;
    margin-bottom: 0;
  }
---

<!-- Slide 1: Title Slide -->

<div style="text-align: center; margin-top: 30px;">
  <span class="tag">Robotics &amp; Machine Learning</span>
  <h1 style="font-size: 40px; margin-top: 14px; margin-bottom: 6px;">ESP32 ML Autonomous RC Car</h1>
  <p style="font-size: 22px; color: #475569; font-weight: 500; margin-bottom: 28px;">
    Behavioral Cloning via Time-of-Flight LiDAR &amp; Real-Time ESP-NOW Telemetry
  </p>

  <div style="display: flex; justify-content: center; gap: 16px; margin-top: 20px;">
    <div class="card" style="width: 190px; text-align: center; padding: 10px;">
      <div style="font-size: 24px;">🚗</div>
      <strong>Physical Car</strong><br><span style="font-size: 14px; color: #64748b;">ESP32 + TB6612FNG</span>
    </div>
    <div class="card" style="width: 190px; text-align: center; padding: 10px;">
      <div style="font-size: 24px;">📡</div>
      <strong>Wireless Link</strong><br><span style="font-size: 14px; color: #64748b;">ESP-NOW @ 50 Hz</span>
    </div>
    <div class="card" style="width: 190px; text-align: center; padding: 10px;">
      <div style="font-size: 24px;">🎯</div>
      <strong>Perception</strong><br><span style="font-size: 14px; color: #64748b;">3× VL53L0X ToF Laser</span>
    </div>
    <div class="card" style="width: 190px; text-align: center; padding: 10px;">
      <div style="font-size: 24px;">🧠</div>
      <strong>Edge Inference</strong><br><span style="font-size: 14px; color: #64748b;">Random Forest ML</span>
    </div>
  </div>
</div>

<!--
Presenter Notes:
- Welcome the audience and introduce the project.
- State the core thesis: achieving real-time autonomous navigation on low-cost hardware through behavioral cloning (imitation learning).
-->

---

<!-- Slide 2: Project Introduction -->

## Project Overview &amp; Objectives

<div class="grid-2-equal">
  <div class="card">
    <h3 style="color: #1e40af;">🎯 The Mission</h3>
    <ul>
      <li><strong>Autonomous Navigation:</strong> Enable a small RC vehicle to drive autonomously around a track without GPS or cameras.</li>
      <li><strong>Behavioral Cloning:</strong> Train machine learning models directly on human driving demonstrations.</li>
      <li><strong>Low-Cost Edge Sensing:</strong> Replace bulky LiDAR or vision systems with lightweight laser Time-of-Flight sensors.</li>
    </ul>
  </div>
  <div class="card">
    <h3 style="color: #047857;">💡 The Core Approach</h3>
    <ul>
      <li><strong>Split Architecture:</strong> Vehicle handles real-time motor control and sensor polling; PC handles machine learning inference.</li>
      <li><strong>Zero-Latency Wireless:</strong> Dedicated ESP-NOW protocol eliminates Wi-Fi router bottlenecks.</li>
      <li><strong>Closed-Loop Safety:</strong> Active front-collision emergency braking and instant human takeover capability.</li>
    </ul>
  </div>
</div>

<div class="highlight-card" style="margin-top: 18px; text-align: center;">
  <strong>Key Result:</strong> Continuous, wall-avoiding autonomous driving achieved purely from 3 distance values.
</div>

<!--
Presenter Notes:
- Explain the motivation: why cameras aren't always needed for simple track navigation.
- Highlight behavioral cloning: learning policies from human demonstrations.
- Mention the distributed design: keeping vehicle payload light by running the model on the host PC over high-speed RF.
-->

---

<!-- Slide 3: The Physical Vehicle Platform -->

## The Physical Robot Platform

<div class="grid-2">
  <div>
    <ul>
      <li><strong>Differential Drive Chassis:</strong> Dual independent DC gear motors with rear low-friction caster wheel.</li>
      <li><strong>Forward Perception Array:</strong> 3× laser Time-of-Flight (ToF) sensors configured in a wide forward cone.</li>
      <li><strong>Dual-Rail Power Isolation:</strong> High-current motor supply decoupled from delicate 3.3V logic and sensors.</li>
      <li><strong>Modular Stack:</strong> Tiered design separating motor drivers, power conversion, and the main MCU.</li>
    </ul>
  </div>
  <div style="text-align: center;">
    <img src="img_front.jpg" alt="Front view of the RC car" style="width: 100%; max-height: 330px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); object-fit: cover;">
  </div>
</div>

<!--
Presenter Notes:
- Point out the physical arrangement in the photo: the front-mounted 3 sensors (angled left, direct forward, angled right).
- Mention the low center of gravity and separate battery placement.
-->

---

<!-- Slide 4: Vehicle Chassis & Hardware Integration -->

## Vehicle Chassis &amp; Hardware Integration

<div class="grid-2">
  <div style="text-align: center;">
    <img src="img_side.jpg" alt="Side view of the RC car" style="width: 100%; max-height: 330px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); object-fit: cover;">
  </div>
  <div>
    <div class="card" style="margin-bottom: 10px;">
      <h3 style="margin-top: 0; font-size: 16px;">Microcontroller (Onboard Node)</h3>
      <p style="margin: 0; font-size: 15px; color: #475569;">
        <strong>WEMOS LOLIN32 v1 (ESP32)</strong> manages I2C sensor polling, PWM generation, and bidirectional RF communication.
      </p>
    </div>
    <div class="card" style="margin-bottom: 10px;">
      <h3 style="margin-top: 0; font-size: 16px;">Motor Actuation</h3>
      <p style="margin: 0; font-size: 15px; color: #475569;">
        <strong>TB6612FNG Dual H-Bridge</strong> driver with high-efficiency MOSFETs for smooth left/right differential steering.
      </p>
    </div>
    <div class="card">
      <h3 style="margin-top: 0; font-size: 16px;">Voltage Step-Down</h3>
      <p style="margin: 0; font-size: 15px; color: #475569;">
        <strong>MP1584 Buck Converter</strong> regulates the high-voltage battery pack down to a clean 5V rail for the ESP32.
      </p>
    </div>
  </div>
</div>

<!--
Presenter Notes:
- Walk through the side view showing the battery pack position, motor driver board, and buck converter.
- Highlight the modularity: components can be replaced or adjusted without dismantling the chassis.
-->

---

<!-- Slide 5: System Architecture -->

## End-to-End System Architecture

<div class="card" style="margin-bottom: 16px; text-align: center; background: #f0f9ff; border-color: #bae6fd; padding: 10px 14px;">
  <span style="font-size: 17px; font-weight: 700; color: #0369a1;">
    Xbox Controller ➔ Host PC (Python ML) ➔ USB Serial ➔ ESP32 Dongle ➔ [ESP-NOW] ➔ Car ESP32 ➔ Motors
  </span>
</div>

<div class="grid-2-equal">
  <div class="card">
    <h3 style="margin-top: 0;">💻 Host Node (PC &amp; Dongle)</h3>
    <ul>
      <li>ESP32 DevKit v1 USB Dongle acts as RF bridge.</li>
      <li>Python reads live telemetry over USB Serial.</li>
      <li>Runs Random Forest inference at ~30 Hz.</li>
      <li>Xbox Controller for training &amp; safety takeover.</li>
    </ul>
  </div>
  <div class="card">
    <h3 style="margin-top: 0;">🚗 Vehicle Edge Node (Car)</h3>
    <ul>
      <li>Reads 3× ToF sensors at ~50 Hz.</li>
      <li>Transmits telemetry packets over ESP-NOW.</li>
      <li>Receives steering commands &amp; generates PWM.</li>
      <li>Failsafe automatic emergency braking.</li>
    </ul>
  </div>
</div>

<!--
Presenter Notes:
- Explain why we split compute: the ESP32 handles low-level real-time I/O (PWM, sensor buses), while the PC handles data recording and ML inference.
- Emphasize the ultra-low latency link connecting both worlds.
-->

---

<!-- Slide 6: Hardware Wiring Schematic -->

## Complete Hardware Wiring Schematic

<div class="grid-2" style="grid-template-columns: 1.3fr 0.7fr;">
  <div style="text-align: center;">
    <img src="wiring_diagram.svg" alt="Hardware Wiring Schematic" style="width: 100%; max-height: 340px; border-radius: 8px; border: 1px solid #cbd5e1; background: #ffffff;">
  </div>
  <div>
    <div class="card" style="margin-bottom: 8px; padding: 8px 12px;">
      <strong style="color: #dc2626; font-size: 15px;">🔴 10V Motor Rail:</strong>
      <div style="font-size: 13px; color: #64748b;">Direct battery feed to TB6612 VM &amp; MP1584 Buck.</div>
    </div>
    <div class="card" style="margin-bottom: 8px; padding: 8px 12px;">
      <strong style="color: #2563eb; font-size: 15px;">🔵 5V Logic In:</strong>
      <div style="font-size: 13px; color: #64748b;">Regulated output from MP1584 into ESP32 VIN pin.</div>
    </div>
    <div class="card" style="margin-bottom: 8px; padding: 8px 12px;">
      <strong style="color: #1d4ed8; font-size: 15px;">⚡ 3.3V Sensor Rail:</strong>
      <div style="font-size: 13px; color: #64748b;">Onboard ESP32 LDO feeds TB6612 logic &amp; 3× VL53L0X.</div>
    </div>
    <div class="card" style="padding: 8px 12px;">
      <strong style="color: #475569; font-size: 15px;">⏚ Common Ground:</strong>
      <div style="font-size: 13px; color: #64748b;">Unified ground plane prevents floating signals.</div>
    </div>
  </div>
</div>

<!--
Presenter Notes:
- Reference the diagram on screen.
- Emphasize safety: the motor high-voltage rail is kept separate from sensitive sensor logic.
- Highlight the common ground requirement for clean I2C and PWM signaling.
-->

---

<!-- Slide 7: Perception Layer - Time-of-Flight Sensors -->

## Perception: 3× VL53L0X Laser ToF Sensors

<div class="grid-2">
  <div>
    <ul>
      <li><strong>Millimeter Precision:</strong> Infrared laser Time-of-Flight ranging (immune to acoustic echoes &amp; color bias).</li>
      <li><strong>Tri-Sensor Angular Coverage:</strong>
        <ul>
          <li><strong>Left:</strong> Angled outward at ~35°–45°</li>
          <li><strong>Center:</strong> Directed straight forward (0°)</li>
          <li><strong>Right:</strong> Angled outward at ~35°–45°</li>
        </ul>
      </li>
      <li><strong>Sequential Dynamic I2C Boot:</strong>
        <ul>
          <li>All sensors boot at default address <code>0x29</code>.</li>
          <li>ESP32 asserts XSHUT LOW to hold them in reset.</li>
          <li>Sensors enabled sequentially and reassigned to <code>0x30</code>, <code>0x31</code>, and <code>0x32</code>.</li>
        </ul>
      </li>
    </ul>
  </div>
  <div style="text-align: center;">
    <img src="VL53L0X.jpg" alt="VL53L0X Time of Flight Sensor" style="width: 70%; max-height: 290px; border-radius: 8px; border: 1px solid #cbd5e1; box-shadow: 0 3px 8px rgba(0,0,0,0.08);">
  </div>
</div>

<!--
Presenter Notes:
- Explain why ultrasonic sensors weren't used: ultrasonics suffer from echo cones, wide blind spots, and slower polling.
- Detail the dynamic addressing: VL53L0X hardcodes 0x29, so we sequentially boot them using XSHUT GPIOs.
-->

---

<!-- Slide 8: Wireless Communication Layer - ESP-NOW -->

## Wireless Bridge: ESP-NOW Protocol

<div class="grid-2" style="grid-template-columns: 1.1fr 0.9fr; align-items: start;">
  <div>
    <ul>
      <li><strong>Connectionless 2.4 GHz RF:</strong> Direct MAC-layer packet protocol bypassing Wi-Fi router &amp; AP overhead.</li>
      <li><strong>Ultra-Low Latency (&lt;3 ms):</strong> Deterministic timing sustaining a real-time <strong>50 Hz</strong> closed loop.</li>
      <li><strong>Uplink (Car ➔ PC):</strong> Streams live 3× ToF LiDAR distance triplets <code>[L, C, R]</code>.</li>
      <li><strong>Downlink (PC ➔ Car):</strong> Delivers ML steering commands &amp; throttle PWM.</li>
      <li><strong>Zero Wi-Fi Dropouts:</strong> Direct peer-to-peer link immune to network congestion.</li>
    </ul>
  </div>
  <div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
      <div class="card" style="text-align: center; padding: 8px 6px;">
        <img src="ESP32_devkit_v1.png" alt="ESP32 DevKit Dongle" style="height: 85px; width: 100%; object-fit: contain;">
        <div style="font-size: 12px; font-weight: 700; color: #1e40af; margin-top: 4px;">PC Dongle</div>
        <div style="font-size: 10px; color: #64748b;">ESP32 DevKit v1</div>
      </div>
      <div class="card" style="text-align: center; padding: 8px 6px;">
        <img src="lolin32.jpg" alt="LOLIN32 Car MCU" style="height: 85px; width: 100%; object-fit: contain;">
        <div style="font-size: 12px; font-weight: 700; color: #1e40af; margin-top: 4px;">Car Node</div>
        <div style="font-size: 10px; color: #64748b;">WEMOS LOLIN32</div>
      </div>
    </div>
    <div class="card" style="margin-top: 10px; text-align: center; background: #f0fdf4; border: 1.5px solid #86efac; padding: 6px 10px;">
      <strong style="color: #15803d; font-size: 13px;">📡 2.4 GHz ESP-NOW Wireless Bridge</strong>
      <div style="font-size: 11px; color: #047857; margin-top: 2px;">Sub-3ms packet latency • Zero router overhead • 50 Hz</div>
    </div>
  </div>
</div>

<!--
Presenter Notes:
- Compare ESP-NOW to standard Wi-Fi / WebSockets: no IP negotiation, no router disconnects, instant packet delivery.
- The dongle eliminates the need for proprietary RF cards; it's a standard USB serial device on the PC.
-->

---

<!-- Slide 9: Behavioral Cloning Pipeline -->

## Step 1: Teleoperation &amp; Data Acquisition

<div class="grid-2-equal">
  <div class="card">
    <h3 style="margin-top: 0;">🎮 Human Demonstration</h3>
    <ul>
      <li>Human pilot drives the car around the walled track using an <strong>Xbox Controller</strong>.</li>
      <li>Smooth cornering demonstrated under real physics (inertia, wall reflections).</li>
      <li>Teleoperation runs via <code>manual_control.py</code>.</li>
    </ul>
  </div>
  <div class="card">
    <h3 style="margin-top: 0;">📊 Synchronized Dataset Logging</h3>
    <ul>
      <li>Telemetry logged continuously during manual driving:</li>
    </ul>
    <div style="background: #f1f5f9; padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 13px; margin-top: 6px;">
      dist_left, dist_center, dist_right ➔ direction<br>
      284, 850, 610 ➔ FORWARD<br>
      142, 380, 790 ➔ FORWARD_RIGHT<br>
      820, 210, 115 ➔ FORWARD_LEFT
    </div>
  </div>
</div>

<!--
Presenter Notes:
- Explain imitation learning: the machine learns the policy by observing a human expert.
- Emphasize data hygiene: we strip timestamps and speed so the model strictly maps spatial geometry to steering decisions.
-->

---

<!-- Slide 10: Machine Learning Model Training -->

## Step 2: Supervised Model Training

<div class="grid-2">
  <div>
    <ul>
      <li><strong>Model:</strong> Random Forest Classifier (Ensemble of Decision Trees).</li>
      <li><strong>Input Features:</strong> Distance triplets <code>[dist_left, dist_center, dist_right]</code> (mm).</li>
      <li><strong>Target Classes:</strong> <code>FORWARD</code>, <code>FORWARD_LEFT</code>, <code>FORWARD_RIGHT</code>.</li>
      <li><strong>Why Random Forest?</strong>
        <ul>
          <li>Handles non-linear spatial boundaries naturally.</li>
          <li>Resistant to sensor noise and transient outliers.</li>
          <li>Sub-millisecond inference time on host CPU.</li>
        </ul>
      </li>
      <li><strong>Model Export:</strong> Serialized into <code>pilot_model.pkl</code> via joblib.</li>
    </ul>
  </div>
  <div class="card" style="text-align: center;">
    <h3 style="margin-top: 0; color: #047857; font-size: 16px;">Decision Logic Concept</h3>
    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
      <div style="background: #ecfdf5; border: 1px solid #a7f3d0; padding: 8px; border-radius: 6px; font-size: 14px;">
        <strong>Obstacle on Left:</strong><br><code>dist_L &lt; dist_R</code> ➔ Steer <strong>FORWARD_RIGHT</strong>
      </div>
      <div style="background: #eff6ff; border: 1px solid #bfdbfe; padding: 8px; border-radius: 6px; font-size: 14px;">
        <strong>Clear Corridor:</strong><br><code>dist_C &gt; threshold</code> ➔ Cruise <strong>FORWARD</strong>
      </div>
      <div style="background: #fef2f2; border: 1px solid #fecaca; padding: 8px; border-radius: 6px; font-size: 14px;">
        <strong>Obstacle on Right:</strong><br><code>dist_R &lt; dist_L</code> ➔ Steer <strong>FORWARD_LEFT</strong>
      </div>
    </div>
  </div>
</div>

<!--
Presenter Notes:
- Explain that Random Forest was chosen because it trains in seconds, doesn't overfit on small datasets, and runs in sub-milliseconds without a GPU.
-->

---

<!-- Slide 11: Autonomous Inference in Action -->

## Step 3: Real-Time Autonomous Autopilot

<div class="grid-2-equal">
  <div class="card">
    <h3 style="margin-top: 0;">⚡ Inference Execution Loop</h3>
    <ul>
      <li><code>autopilot.py</code> receives live ToF triplets from the dongle.</li>
      <li>Evaluates input vector against <code>pilot_model.pkl</code>.</li>
      <li>Predicts steering action with high confidence at <strong>~30 Hz</strong>.</li>
      <li>Dispatches instantaneous command frame back over ESP-NOW.</li>
    </ul>
  </div>
  <div class="card">
    <h3 style="margin-top: 0;">🛡️ Active Safety &amp; Failsafes</h3>
    <ul>
      <li><strong>Collision Brake:</strong> Hard stop triggered if front distance drops below safety buffer (<code>&lt; 120 mm</code>).</li>
      <li><strong>Human Safety Override:</strong> Touching any analog stick on the Xbox controller instantly yields manual control.</li>
      <li><strong>Heartbeat Timeout:</strong> Car stops automatically if RF connection is lost for &gt;500 ms.</li>
    </ul>
  </div>
</div>

<!--
Presenter Notes:
- Walk through the safety features: emergency braking, manual controller priority override, and loss-of-signal auto-stop.
- This ensures testing is safe and won't damage the robot against walls.
-->

---

<!-- Slide 12: Demonstration Video -->

## Autonomous Lap Demonstration

<div style="text-align: center; margin-top: 6px;">
  <video controls width="720" style="max-height: 350px; border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); border: 2px solid #cbd5e1;" preload="metadata">
    <source src="autopilot.mp4" type="video/mp4">
    Your browser does not support the video tag.
  </video>
  <p style="font-size: 15px; color: #64748b; margin-top: 8px; font-weight: 500;">
    📹 <strong>Live Track Run:</strong> Zero human intervention — steering dynamically adjusts based on live 3× ToF readings.
  </p>
</div>

<!--
Presenter Notes:
- Play the video during the oral presentation.
- Point out how smoothly the car negotiates the track corners.
- Mention that the throttle remains steady while steering commands pulse adaptively.
-->

---

<!-- Slide 13: Summary & Key Takeaways -->

## Summary &amp; Key Takeaways

<div class="card" style="margin-bottom: 18px; padding: 18px 24px;">
  <h3 style="color: #1e40af; font-size: 21px; margin-bottom: 12px;">🏆 Core Project Achievements</h3>
  <ul>
    <li><strong>End-to-End Imitation Learning:</strong> Demonstrated that complex wall-following and obstacle navigation can be learned purely from human telemetry.</li>
    <li><strong>Low-Cost, High-Precision Perception:</strong> 3× laser Time-of-Flight sensors provide reliable millimeter ranging without heavy vision processing.</li>
    <li><strong>Zero-Overhead RF Pipeline:</strong> ESP-NOW delivers deterministic &lt;3 ms latency for real-time 50 Hz closed-loop control.</li>
    <li><strong>Robust Safety Architecture:</strong> Triple-layer failsafes ensure active collision prevention and seamless human intervention.</li>
  </ul>
</div>

<div style="text-align: center; margin-top: 24px;">
  <span style="font-size: 24px; font-weight: 800; color: #1e3a8a;">Thank You — Questions &amp; Discussion</span>
</div>

<!--
Presenter Notes:
- Conclude by summarizing the key achievements of the project.
- Reiterate how the combination of simple laser sensors, high-speed wireless, and random forest inference creates a reliable autonomous platform.
- Invite questions from the audience.
-->
