#!/usr/bin/env python3
"""
control.py - Pygame Xbox Controller Teleoperation for ESP32 RC Car
Reads an Xbox wired controller via Pygame and streams drive commands
(<steer>,<throttle>) over USB Serial to the ESP32.
"""

import sys
import time
import argparse
import glob

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: 'pyserial' library not found.")
    print("Please install it via: pip install pyserial (or uv add pyserial)")
    sys.exit(1)

try:
    import pygame
except ImportError:
    print("Error: 'pygame' library not found.")
    print("Please install it via: pip install pygame (or uv add pygame)")
    sys.exit(1)


def auto_detect_serial_port():
    """Detect common ESP32 USB serial ports on Linux."""
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if ports:
        return ports[0]
    available = [p.device for p in serial.tools.list_ports.comports()]
    if available:
        return available[0]
    return "/dev/ttyUSB0"


def apply_deadzone(value, threshold=0.08):
    """Zero out small jitter around joystick center."""
    if abs(value) < threshold:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * ((abs(value) - threshold) / (1.0 - threshold))


def normalize_trigger(axis_val):
    """
    Normalizes trigger axis from [-1.0, 1.0] (unpressed=-1.0, pressed=+1.0)
    to [0.0, 1.0].
    """
    return max(0.0, (axis_val + 1.0) / 2.0)


def main():
    parser = argparse.ArgumentParser(description="Xbox Controller Teleop (Pygame)")
    parser.add_argument(
        "--port", type=str, default=None, help="Serial port (e.g. /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        "--rate", type=float, default=30.0, help="Command send rate in Hz (default: 30)"
    )
    parser.add_argument(
        "--deadzone", type=float, default=0.08, help="Stick deadzone (default: 0.08)"
    )
    parser.add_argument(
        "--invert-steer", action="store_true", help="Invert steering axis"
    )
    parser.add_argument(
        "--invert-throttle", action="store_true", help="Invert stick throttle axis"
    )
    args = parser.parse_args()

    # 1. Connect to ESP32 Serial
    port = args.port if args.port else auto_detect_serial_port()
    print(f"Connecting to ESP32 on {port} at {args.baud} baud...")

    try:
        ser = serial.Serial(port, args.baud, timeout=0.1)
        time.sleep(1.5)  # Wait for ESP32 boot
        ser.reset_input_buffer()
        print("Serial connection established.")
    except Exception as e:
        print(f"Failed to open serial port '{port}': {e}")
        print("Tip: Run 'sudo usermod -aG dialout $USER' or check connection.")
        sys.exit(1)

    # 2. Initialize Pygame Joystick
    pygame.init()
    pygame.joystick.init()

    joystick_count = pygame.joystick.get_count()
    if joystick_count == 0:
        print("Error: No Xbox controller / joystick detected by Pygame!")
        print("Please connect your controller via USB and run again.")
        ser.close()
        sys.exit(1)

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(
        f"Connected to Controller: '{joystick.get_name()}' ({joystick.get_numaxes()} axes, {joystick.get_numbuttons()} buttons)"
    )

    print("\nControls:")
    print("  • Left Stick X: Steering (Left / Right)")
    print("  • Left Stick Y: Throttle (Forward / Reverse)")
    print("  • Right Trigger (RT): Forward Throttle (Alternative)")
    print("  • Left Trigger (LT):  Reverse Throttle (Alternative)")
    print("  • 'B' Button: Emergency Brake / Stop")
    print("  • Ctrl+C: Exit safely\n")

    send_interval = 1.0 / args.rate

    try:
        while True:
            start_time = time.time()
            pygame.event.pump()

            # Read Buttons for emergency brake (B is button 1 on standard Xbox layout)
            b_button = False
            if joystick.get_numbuttons() > 1:
                b_button = bool(joystick.get_button(1))

            # 1. Steering: Left Stick X (Axis 0)
            raw_steer = joystick.get_axis(0)
            steer = apply_deadzone(raw_steer, args.deadzone)
            if args.invert_steer:
                steer = -steer

            # 2. Stick Throttle: Left Stick Y (Axis 1) - Pushing forward is negative in Pygame
            raw_stick_y = -joystick.get_axis(1)
            stick_throttle = apply_deadzone(raw_stick_y, args.deadzone)
            if args.invert_throttle:
                stick_throttle = -stick_throttle

            # 3. Trigger Throttle: RT (Axis 5) and LT (Axis 2 or Axis 4)
            trigger_throttle = 0.0
            num_axes = joystick.get_numaxes()
            if num_axes >= 6:
                rt_val = normalize_trigger(joystick.get_axis(5))
                lt_axis = 2 if num_axes == 6 else 4
                lt_val = normalize_trigger(joystick.get_axis(lt_axis))

                if rt_val > 0.05:
                    trigger_throttle += rt_val
                if lt_val > 0.05:
                    trigger_throttle -= lt_val

            # Use triggers if engaged, otherwise analog stick
            throttle = (
                trigger_throttle if abs(trigger_throttle) > 0.05 else stick_throttle
            )

            # 4. Emergency Brake Override
            if b_button:
                steer = 0.0
                throttle = 0.0
                status_note = "[BRAKE ENGAGED]"
            else:
                status_note = "[DRIVING]       "

            # Clamp
            steer = max(-1.0, min(1.0, steer))
            throttle = max(-1.0, min(1.0, throttle))

            # Send command to ESP32
            cmd_str = f"{steer:.2f},{throttle:.2f}\n"
            ser.write(cmd_str.encode("utf-8"))

            # Visual progress bars in console
            s_bar = int((steer + 1.0) * 10)
            t_bar = int((throttle + 1.0) * 10)
            steer_vis = "[" + "#" * s_bar + " " * (20 - s_bar) + "]"
            throttle_vis = "[" + "#" * t_bar + " " * (20 - t_bar) + "]"

            sys.stdout.write(
                f"\r{status_note} | Steer: {steer:+0.2f} {steer_vis} | Throttle: {throttle:+0.2f} {throttle_vis} "
            )
            sys.stdout.flush()

            # Maintain update rate
            elapsed = time.time() - start_time
            sleep_time = max(0.0, send_interval - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\nExiting teleoperation...")
    finally:
        print("Sending stop command to vehicle...")
        try:
            for _ in range(5):
                ser.write(b"0.0,0.0\n")
                ser.write(b"x\n")
                time.sleep(0.05)
            ser.close()
        except Exception:
            pass
        pygame.quit()
        print("Safely disconnected.")


if __name__ == "__main__":
    main()
