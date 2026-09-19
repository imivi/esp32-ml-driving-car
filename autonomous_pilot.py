#!/usr/bin/env python3
"""
autonomous_pilot.py - Autonomous Driving Inference for ESP32 RC Car

Loads the trained Random Forest classifier (pilot_model.pkl), listens to live
distance sensor telemetry (dist_left, dist_center, dist_right) from the car,
runs real-time inference to determine direction (FORWARD, FORWARD_LEFT, FORWARD_RIGHT),
and streams steering and throttle commands back to the vehicle.

Features:
  • Real-time ML inference using Random Forest
  • Emergency front collision braking (if center distance < threshold)
  • Optional Xbox controller dead-man switch / manual override
  • Simulation / playback mode (--simulate) for offline testing
  • Live terminal dashboard with sensor bars and confidence probabilities
"""

import os
import sys
import time
import argparse
import glob
import warnings
from datetime import datetime

# Filter benign sklearn feature name warnings during high-frequency inference
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import joblib
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"Error: Missing required library: {e}")
    print("Please install requirements using: uv add scikit-learn pandas joblib")
    sys.exit(1)


def auto_detect_serial_port():
    """Detect ESP32 USB serial port across Windows, Linux, and macOS."""
    try:
        import serial.tools.list_ports

        ports = list(serial.tools.list_ports.comports())
        if not ports:
            linux_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
            return linux_ports[0] if linux_ports else None

        keywords = [
            "cp210",
            "ch340",
            "ch341",
            "ftdi",
            "espressif",
            "esp32",
            "usb to uart",
            "usb serial",
        ]
        valid_ports = [
            p
            for p in ports
            if "bthenum" not in (p.hwid or "").lower()
            and "bluetooth" not in (p.description or "").lower()
        ]

        for p in valid_ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in keywords):
                return p.device

        for p in valid_ports:
            if p.vid is not None or "usb" in (p.hwid or "").lower():
                return p.device

        return valid_ports[0].device if valid_ports else None
    except Exception:
        linux_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        return linux_ports[0] if linux_ports else None


class AutonomousPilot:
    def __init__(
        self,
        model_path: str = "pilot_model.pkl",
        speed: float = 0.85,
        steer_angle: float = 0.55,
        brake_dist_mm: int = 140,
    ):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model file '{model_path}' not found. Please train it first with: python train.py"
            )

        print(f"Loading trained classifier from '{model_path}'...")
        artifact = joblib.load(model_path)
        self.model = (
            artifact["model"]
            if isinstance(artifact, dict) and "model" in artifact
            else artifact
        )
        self.feature_names = (
            artifact.get(
                "feature_names", ["dist_left_mm", "dist_center_mm", "dist_right_mm"]
            )
            if isinstance(artifact, dict)
            else ["dist_left_mm", "dist_center_mm", "dist_right_mm"]
        )
        self.classes = list(self.model.classes_)
        self.speed = speed
        self.steer_angle = steer_angle
        self.brake_dist_mm = brake_dist_mm

        print(f"Model loaded successfully! Supported directions: {self.classes}")

    def predict_direction(self, dist_left: int, dist_center: int, dist_right: int):
        """
        Runs model inference on sensor readings.
        Returns (predicted_direction, confidence_prob, class_probabilities_dict)
        """
        features_df = pd.DataFrame(
            [[dist_left, dist_center, dist_right]], columns=self.feature_names
        )
        pred_label = self.model.predict(features_df)[0]

        prob_dict = {}
        confidence = 1.0
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(features_df)[0]
            prob_dict = {cls: float(prob) for cls, prob in zip(self.classes, probs)}
            confidence = float(np.max(probs))

        return pred_label, confidence, prob_dict

    def direction_to_controls(self, direction: str, dist_center: int):
        """
        Maps direction label to target (steer, throttle) with collision safety override.
        """
        # Emergency collision braking if front obstacle is closer than threshold
        if 0 < dist_center < self.brake_dist_mm:
            return 0.0, 0.0, "[EMERGENCY BRAKE: OBSTACLE AHEAD]"

        if direction == "FORWARD":
            steer = 0.0
            throttle = self.speed
            status = "[AUTOPILOT: FORWARD]"
        elif direction == "FORWARD_LEFT":
            steer = -self.steer_angle
            throttle = self.speed * 0.90
            status = "[AUTOPILOT: STEER LEFT]"
        elif direction == "FORWARD_RIGHT":
            steer = self.steer_angle
            throttle = self.speed * 0.90
            status = "[AUTOPILOT: STEER RIGHT]"
        else:
            steer = 0.0
            throttle = 0.0
            status = f"[AUTOPILOT: UNKNOWN {direction}]"

        return steer, throttle, status


def run_simulation(
    pilot: AutonomousPilot,
    csv_path: str = "track_data.csv",
    delay: float = 0.01,
    limit: int = None,
):
    """Simulates inference playback using historical data from track_data.csv."""
    if not os.path.exists(csv_path):
        print(f"Simulation file '{csv_path}' not found.")
        return

    print(f"\n--- Starting Offline Simulation on '{csv_path}' ---")
    print("Simulating sensor telemetry stream and evaluating model decisions...\n")
    time.sleep(0.5)

    df = pd.read_csv(csv_path)
    if limit and limit > 0:
        df = df.head(limit)

    correct_count = 0
    total_evaluated = 0

    try:
        for idx, row in df.iterrows():
            dL = int(row["dist_left_mm"])
            dC = int(row["dist_center_mm"])
            dR = int(row["dist_right_mm"])
            actual_dir = str(row.get("direction", "N/A"))

            pred_dir, conf, _ = pilot.predict_direction(dL, dC, dR)
            steer, throttle, status = pilot.direction_to_controls(pred_dir, dC)

            if actual_dir in pilot.classes:
                total_evaluated += 1
                if pred_dir == actual_dir:
                    correct_count += 1

            match_symbol = "✓" if pred_dir == actual_dir else "✗"
            acc_pct = (
                (correct_count / total_evaluated * 100) if total_evaluated > 0 else 0
            )

            # Terminal visual bar
            sys.stdout.write(
                f"\rRow {idx:4d}/{len(df)} | L:{dL:4d} C:{dC:4d} R:{dR:4d}mm | "
                f"Pred: {pred_dir:<13} ({conf * 100:4.1f}%) | "
                f"Actual: {actual_dir:<13} {match_symbol} | "
                f"Steer: {steer:+0.2f} Thr: {throttle:0.2f} | Acc: {acc_pct:5.1f}% "
            )
            sys.stdout.flush()
            if delay > 0:
                time.sleep(delay)

        print(
            f"\n\nSimulation complete! Overall prediction agreement: {acc_pct:.2f}%\n"
        )
    except KeyboardInterrupt:
        print("\nSimulation aborted by user.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous Driving Pilot for ESP32 RC Car using Random Forest"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="pilot_model.pkl",
        help="Path to trained model artifact (default: pilot_model.pkl)",
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Serial port of transmitter dongle (e.g. /dev/ttyUSB0 or COM3)",
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Serial baud rate (default: 115200)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.85,
        help="Autonomous base cruising throttle (0.0 to 1.0, default: 0.85)",
    )
    parser.add_argument(
        "--steer-angle",
        type=float,
        default=0.55,
        help="Steering intensity for turns (0.0 to 1.0, default: 0.55)",
    )
    parser.add_argument(
        "--brake-dist",
        type=int,
        default=140,
        help="Emergency collision brake distance in mm (default: 140 mm / 14 cm)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=30.0,
        help="Command stream loop rate in Hz (default: 30 Hz)",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run offline playback simulation using track_data.csv instead of connecting to serial",
    )
    parser.add_argument(
        "--sim-file",
        type=str,
        default="track_data.csv",
        help="CSV file for offline simulation (default: track_data.csv)",
    )
    parser.add_argument(
        "--sim-limit",
        type=int,
        default=None,
        help="Limit number of rows to simulate (default: all)",
    )
    parser.add_argument(
        "--sim-delay",
        type=float,
        default=0.01,
        help="Delay in seconds between simulation rows (default: 0.01s)",
    )
    args = parser.parse_args()

    # 1. Initialize Autonomous Pilot
    try:
        pilot = AutonomousPilot(
            model_path=args.model,
            speed=args.speed,
            steer_angle=args.steer_angle,
            brake_dist_mm=args.brake_dist,
        )
    except Exception as e:
        print(f"Error initializing pilot: {e}")
        sys.exit(1)

    # If simulation requested, run offline verification and exit
    if args.simulate:
        run_simulation(
            pilot,
            csv_path=args.sim_file,
            delay=args.sim_delay,
            limit=args.sim_limit,
        )
        return

    # 2. Connect to ESP32 Serial
    try:
        import serial
    except ImportError:
        print("Error: 'pyserial' library not found. Install via: uv add pyserial")
        sys.exit(1)

    port = args.port if args.port else auto_detect_serial_port()
    if not port:
        print("Error: No ESP32 USB transmitter detected.")
        print("Tip: Specify manually with --port (e.g. --port /dev/ttyUSB0 or COM3)")
        print(
            "     Or run in offline simulation mode: python autonomous_pilot.py --simulate"
        )
        sys.exit(1)

    print("=================================================")
    print(f" [AUTONOMOUS PILOT MODE]")
    print(f" Serial Port: {port} @ {args.baud} baud")
    print(f" Base Speed:  {args.speed * 100:.0f}%")
    print(f" Turn Angle:  {args.steer_angle * 100:.0f}%")
    print(f" Front Brake: < {args.brake_dist} mm")
    print(" Safety:      Press 'B' on Xbox Controller or Ctrl+C to STOP")
    print("=================================================\n")

    try:
        ser = serial.Serial(port, args.baud, timeout=0.05)
        try:
            ser.dtr = False
            ser.rts = False
        except Exception:
            pass
        time.sleep(1.0)
        ser.reset_input_buffer()
        print(f"Serial connection to transmitter on {port} established.")
    except Exception as e:
        print(f"Failed to open serial port '{port}': {e}")
        sys.exit(1)

    # 3. Optional Xbox Controller for Emergency Stop / Manual Override
    has_controller = False
    controller = None
    try:
        import pygame

        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            controller = pygame.joystick.Joystick(0)
            controller.init()
            has_controller = True
            print(f"Gamepad detected: '{controller.get_name()}'")
            print("  • Press 'B' button for Instant Emergency Stop")
            print("  • Move Left Stick to manually override autopilot\n")
    except Exception:
        pass

    if not has_controller:
        print("No gamepad connected. Autopilot will run fully autonomously.")
        print("Press Ctrl+C in terminal for Emergency Stop.\n")

    # State tracking
    current_distances = {"L": -1, "C": -1, "R": -1}
    last_telemetry_time = time.time()
    send_interval = 1.0 / max(5.0, args.rate)

    def send_command(steer_val: float, throttle_val: float):
        cmd = f"{steer_val:.2f},{throttle_val:.2f}\n".encode("utf-8")
        try:
            ser.write(cmd)
        except Exception:
            pass

    def stop_car():
        for _ in range(5):
            send_command(0.0, 0.0)
            try:
                ser.write(b"x\n")
            except Exception:
                pass
            time.sleep(0.02)

    try:
        while True:
            loop_start = time.time()

            # Process pygame events if controller is present
            if has_controller:
                pygame.event.pump()

            # Check Controller Emergency Stop / Manual Override
            emergency_brake_pressed = False
            manual_override = False
            manual_steer = 0.0
            manual_throttle = 0.0

            if has_controller and controller:
                if controller.get_numbuttons() > 1 and controller.get_button(1):
                    emergency_brake_pressed = True

                stick_x = controller.get_axis(0)
                stick_y = (
                    -controller.get_axis(1) if controller.get_numaxes() > 1 else 0.0
                )
                if abs(stick_x) > 0.15 or abs(stick_y) > 0.15:
                    manual_override = True
                    manual_steer = stick_x
                    manual_throttle = stick_y

            # Read all incoming telemetry packets from Serial
            try:
                while ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("TELEM:"):
                        parts = line[6:].split(",")
                        if len(parts) >= 3:
                            dL = int(parts[0])
                            dC = int(parts[1])
                            dR = int(parts[2])
                            current_distances["L"] = dL if dL < 8000 else -1
                            current_distances["C"] = dC if dC < 8000 else -1
                            current_distances["R"] = dR if dR < 8000 else -1
                            last_telemetry_time = time.time()
            except Exception:
                pass

            dL = current_distances["L"]
            dC = current_distances["C"]
            dR = current_distances["R"]

            # Failsafe: If no telemetry received for > 1.0s, halt vehicle
            is_telemetry_stale = (time.time() - last_telemetry_time) > 1.0

            # Decide Action
            if emergency_brake_pressed:
                steer, throttle = 0.0, 0.0
                status = "[MANUAL BRAKE: B PRESSED]"
                pred_label, confidence = "STOP", 1.0
            elif manual_override:
                steer, throttle = manual_steer, manual_throttle
                status = "[MANUAL JOYSTICK OVERRIDE]"
                pred_label, confidence = "MANUAL", 1.0
            elif is_telemetry_stale:
                steer, throttle = 0.0, 0.0
                status = "[FAILSFE: NO TELEMETRY STREAM]"
                pred_label, confidence = "IDLE", 0.0
            else:
                # RUN MACHINE LEARNING INFERENCE
                pred_label, confidence, prob_dict = pilot.predict_direction(dL, dC, dR)
                steer, throttle, status = pilot.direction_to_controls(pred_label, dC)

            # Send actuation commands to car
            send_command(steer, throttle)

            # Visual Display on Terminal
            def fmt_dist(d):
                return f"{d:4d}mm" if d > 0 else "   -- "

            s_bar = int((steer + 1.0) * 8)
            steer_vis = "[" + "#" * s_bar + " " * (16 - s_bar) + "]"

            sys.stdout.write(
                f"\rL: {fmt_dist(dL)} | C: {fmt_dist(dC)} | R: {fmt_dist(dR)} | "
                f"Model: {pred_label:<13} ({confidence * 100:4.1f}%) | "
                f"Steer: {steer:+0.2f} {steer_vis} Thr: {throttle:0.2f} | {status:<30}"
            )
            sys.stdout.flush()

            # Maintain target loop rate
            elapsed = time.time() - loop_start
            sleep_time = max(0.0, send_interval - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\nAutopilot stopped by user.")
    finally:
        print("Sending safety stop packets to vehicle...")
        stop_car()
        try:
            ser.close()
        except Exception:
            pass
        if has_controller:
            try:
                pygame.quit()
            except Exception:
                pass
        print("Vehicle safely stopped. Pilot shutdown complete.")


if __name__ == "__main__":
    main()
