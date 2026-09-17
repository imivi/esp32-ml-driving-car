#!/usr/bin/env python3
"""
control.py - Pygame Xbox Controller Teleoperation for ESP32 RC Car
Reads an Xbox wired/wireless controller via Pygame and streams drive commands
(<steer>,<throttle>) over USB Serial to the ESP32 WROOM Transmitter Dongle.
The transmitter forwards commands wirelessly to the RC Car (LOLIN32) via ESP-NOW.

Fully supports Windows, Linux, and macOS.
"""

import os
import sys
import time
import argparse
import glob

# Ensure joystick events are processed even without a focused display window
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

try:
    import pygame
except ImportError:
    print("Error: 'pygame' library not found.")
    print("Please install it via: pip install pygame (or uv add pygame)")
    sys.exit(1)


def auto_detect_serial_port():
    """
    Detect ESP32 USB serial port across Windows, Linux, and macOS.
    Prioritizes known ESP32 USB-UART bridges (CP210x, CH340, FTDI, Espressif CDC).
    """
    try:
        import serial.tools.list_ports

        ports = list(serial.tools.list_ports.comports())
        if not ports:
            # Fallback to Linux device nodes if comports finds nothing
            linux_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
            return linux_ports[0] if linux_ports else None

        # Priority 1: Match known ESP32 USB-UART bridge identifiers
        keywords = [
            "cp210",
            "ch340",
            "ch341",
            "ch9102",
            "ftdi",
            "espressif",
            "esp32",
            "silicon labs",
            "wch",
            "usb to uart",
            "usb-to-uart",
            "usb serial",
        ]
        known_vids = {0x10C4, 0x1A86, 0x0403, 0x303A, 0x2341, 0x2E8A}

        # Filter out virtual Bluetooth COM ports
        valid_ports = [
            p for p in ports
            if "bthenum" not in (p.hwid or "").lower()
            and "bluetooth" not in (p.description or "").lower()
        ]

        for p in valid_ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            mfg = (p.manufacturer or "").lower()
            if (p.vid and p.vid in known_vids) or any(
                k in desc or k in hwid or k in mfg for k in keywords
            ):
                return p.device

        # Priority 2: Any USB serial port (excludes internal motherboard COM ports like COM1)
        for p in valid_ports:
            if p.vid is not None or "usb" in (p.hwid or "").lower():
                return p.device

        # Priority 3: On Windows, prefer any non-Bluetooth port other than COM1
        if sys.platform.startswith("win"):
            non_com1 = [p.device for p in valid_ports if p.device.upper() != "COM1"]
            if non_com1:
                return non_com1[0]

        return valid_ports[0].device if valid_ports else None
    except ImportError:
        linux_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        return linux_ports[0] if linux_ports else None
    except Exception:
        return None


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


class ControllerReader:
    """
    Unified Xbox Controller reader for Windows, Linux, and macOS.
    Prefers pygame._sdl2.controller (GameController API) for normalized cross-platform axes,
    falling back to standard pygame.joystick.
    """

    def __init__(self):
        self.mode = None
        self.ctrl = None
        self.joy = None
        self.name = "Unknown"
        self.axes_count = 0
        self.buttons_count = 0

        # Try SDL2 GameController API first
        try:
            import pygame._sdl2.controller as sdl2_ctrl

            sdl2_ctrl.init()
            if sdl2_ctrl.get_count() > 0 and sdl2_ctrl.is_controller(0):
                self.ctrl = sdl2_ctrl.Controller(0)
                self.ctrl.init()
                self.mode = "sdl2"
                self.name = self.ctrl.name or "Xbox Controller (SDL2)"
                self.axes_count = 6
                self.buttons_count = 15
                return
        except Exception:
            pass

        # Fallback to standard pygame.joystick
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joy = pygame.joystick.Joystick(0)
            self.joy.init()
            self.mode = "joystick"
            self.name = self.joy.get_name()
            self.axes_count = self.joy.get_numaxes()
            self.buttons_count = self.joy.get_numbuttons()

            # Determine trigger axis numbers based on OS and axis count:
            # Windows XInput: Axis 0=LeftX, 1=LeftY, 2=RightX, 3=RightY, 4=LT, 5=RT
            # Linux xpad:     Axis 0=LeftX, 1=LeftY, 2=LT,     3=RightX, 4=RightY, 5=RT
            is_win = sys.platform.startswith("win")
            if is_win:
                self.lt_axis = 4 if self.axes_count >= 6 else (2 if self.axes_count == 5 else 2)
                self.rt_axis = 5 if self.axes_count >= 6 else (2 if self.axes_count == 5 else 5)
            else:
                self.lt_axis = 2 if self.axes_count == 6 else 4
                self.rt_axis = 5

    def is_connected(self):
        return self.mode is not None

    def read_inputs(self, deadzone=0.08, invert_steer=False, invert_throttle=False):
        """
        Returns (steer, throttle, b_button)
        steer in [-1.0, 1.0], throttle in [-1.0, 1.0], b_button is bool
        """
        if self.mode == "sdl2":
            # SDL2 GameController API: normalized integer range -32768..32767 for sticks,
            # and 0..32767 for triggers
            raw_steer = self.ctrl.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / 32767.0
            steer = apply_deadzone(raw_steer, deadzone)
            if invert_steer:
                steer = -steer

            # Stick throttle
            raw_stick_y = -(self.ctrl.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32767.0)
            stick_throttle = apply_deadzone(raw_stick_y, deadzone)

            # Triggers: 0 to 32767 (RT = Forward, LT = Reverse)
            rt_raw = max(0.0, self.ctrl.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) / 32767.0)
            lt_raw = max(0.0, self.ctrl.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT) / 32767.0)

            trigger_throttle = 0.0
            if rt_raw > 0.05:
                trigger_throttle += rt_raw
            if lt_raw > 0.05:
                trigger_throttle -= lt_raw

            throttle = trigger_throttle if abs(trigger_throttle) > 0.05 else stick_throttle
            if invert_throttle:
                throttle = -throttle

            b_button = bool(self.ctrl.get_button(pygame.CONTROLLER_BUTTON_B))

            return steer, throttle, b_button

        elif self.mode == "joystick":
            # 1. Steering: Left Stick X (Axis 0)
            raw_steer = self.joy.get_axis(0)
            steer = apply_deadzone(raw_steer, deadzone)
            if invert_steer:
                steer = -steer

            # 2. Stick Throttle: Left Stick Y (Axis 1)
            raw_stick_y = -self.joy.get_axis(1)
            stick_throttle = apply_deadzone(raw_stick_y, deadzone)

            # 3. Trigger Throttle
            trigger_throttle = 0.0
            if self.axes_count >= 6:
                rt_val = normalize_trigger(self.joy.get_axis(self.rt_axis))
                lt_val = normalize_trigger(self.joy.get_axis(self.lt_axis))
                if rt_val > 0.05:
                    trigger_throttle += rt_val
                if lt_val > 0.05:
                    trigger_throttle -= lt_val
            elif self.axes_count == 5:
                # Combined trigger axis on legacy DirectInput
                combined = self.joy.get_axis(2)
                if abs(combined) > 0.05:
                    trigger_throttle = -combined

            throttle = trigger_throttle if abs(trigger_throttle) > 0.05 else stick_throttle
            if invert_throttle:
                throttle = -throttle

            # B button: standard button index 1
            b_button = False
            if self.buttons_count > 1:
                b_button = bool(self.joy.get_button(1))

            return steer, throttle, b_button

        return 0.0, 0.0, False


def main():
    # Enable ANSI escape sequences and virtual terminal processing on Windows
    if sys.platform.startswith("win"):
        os.system("")

    parser = argparse.ArgumentParser(
        description="Xbox Controller Teleop -> ESP32 WROOM Transmitter (ESP-NOW)"
    )
    # Serial Port Options
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="USB Serial port of ESP32 WROOM Transmitter (e.g. COM3 on Windows, /dev/ttyUSB0 on Linux)",
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Serial baud rate (default: 115200)"
    )
    # Control Options
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

    # USB Serial Connection to ESP32 WROOM Transmitter
    try:
        import serial
    except ImportError:
        print("Error: 'pyserial' library not found. Install with: uv add pyserial")
        sys.exit(1)

    port = args.port if args.port else auto_detect_serial_port()
    if not port:
        if sys.platform.startswith("win"):
            print("Error: No ESP32 USB transmitter dongle detected (e.g. COM3, COM4).")
            print("Please plug the ESP32 WROOM transmitter into your PC via USB,")
            print("or specify the port manually: uv run control.py --port COM3")
        else:
            print("Error: No USB serial port detected (/dev/ttyUSB* or /dev/ttyACM*).")
            print("Please plug the ESP32 WROOM transmitter into your PC, or specify:")
            print("   uv run control.py --port /dev/ttyUSB0")

        try:
            import serial.tools.list_ports

            available_ports = [
                p for p in serial.tools.list_ports.comports()
                if "bthenum" not in (p.hwid or "").lower()
            ]
            if available_ports:
                print("\nAvailable USB COM ports detected on system:")
                for p in available_ports:
                    print(f"  - {p.device}: {p.description}")
        except Exception:
            pass

        sys.exit(1)

    print("=================================================")
    print(f" [MODE: ESP-NOW Wireless Bridge]")
    print(f" Transmitter Dongle: {port} @ {args.baud} baud")
    print(f" PC (USB) -> ESP32 WROOM -> [ESP-NOW] -> LOLIN32 RC Car")
    print("=================================================\n")

    try:
        ser = serial.Serial(port, args.baud, timeout=0.1)
        # De-assert DTR / RTS to ensure ESP32 does not stay held in reset / bootloader
        try:
            ser.dtr = False
            ser.rts = False
        except Exception:
            pass
        time.sleep(1.0)  # Wait for ESP32 boot
        ser.reset_input_buffer()
        print(f"Serial connection to transmitter on {port} established.")
    except Exception as e:
        print(f"Failed to open serial port '{port}': {e}")
        if sys.platform.startswith("win"):
            print("Tip: Check Windows Device Manager for the correct COM port.")
        else:
            print("Tip: Check USB connection and user permissions (e.g. dialout group).")
        sys.exit(1)

    # Initialize Pygame and Controller
    pygame.init()
    controller = ControllerReader()

    if not controller.is_connected():
        print("Error: No Xbox controller detected by Pygame!")
        print("Please connect your controller via USB/Bluetooth and run again.")
        if ser:
            ser.close()
        sys.exit(1)

    print(
        f"Connected to Controller: '{controller.name}' (Backend: {controller.mode.upper()}, {controller.axes_count} axes, {controller.buttons_count} buttons)"
    )

    print("\nControls:")
    print("  • Left Stick X: Steering (Left / Right)")
    print("  • Left Stick Y: Throttle (Forward / Reverse)")
    print("  • Right Trigger (RT): Forward Throttle (Alternative)")
    print("  • Left Trigger (LT):  Reverse Throttle (Alternative)")
    print("  • 'B' Button: Emergency Brake / Stop")
    print("  • Ctrl+C: Exit safely\n")

    send_interval = 1.0 / args.rate

    def send_packet(data_str):
        raw = data_str.encode("utf-8")
        if ser:
            try:
                ser.write(raw)
            except Exception:
                pass

    # Distance telemetry state (in cm)
    tof_dists = {"L": None, "C": None, "R": None}

    def read_telemetry():
        if not ser or ser.in_waiting == 0:
            return
        try:
            while ser.in_waiting > 0:
                raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
                if raw_line.startswith("TELEM:"):
                    # Format: TELEM:<left_mm>,<center_mm>,<right_mm>,<seq>
                    parts = raw_line[6:].split(",")
                    if len(parts) >= 3:
                        dL = int(parts[0])
                        dC = int(parts[1])
                        dR = int(parts[2])
                        tof_dists["L"] = f"{dL/10.0:.1f}cm" if dL < 8000 else "--"
                        tof_dists["C"] = f"{dC/10.0:.1f}cm" if dC < 8000 else "--"
                        tof_dists["R"] = f"{dR/10.0:.1f}cm" if dR < 8000 else "--"
        except Exception:
            pass

    try:
        while True:
            start_time = time.time()
            pygame.event.pump()

            # Read any incoming sensor telemetry from the vehicle
            read_telemetry()

            steer, throttle, b_button = controller.read_inputs(
                deadzone=args.deadzone,
                invert_steer=args.invert_steer,
                invert_throttle=args.invert_throttle,
            )

            # Emergency Brake Override
            if b_button:
                steer = 0.0
                throttle = 0.0
                status_note = "[BRAKE ENGAGED]"
            else:
                status_note = "[DRIVING]       "

            # Clamp
            steer = max(-1.0, min(1.0, steer))
            throttle = max(-1.0, min(1.0, throttle))

            # Send command to transmitter dongle
            cmd_str = f"{steer:.2f},{throttle:.2f}\n"
            send_packet(cmd_str)

            # Visual progress bars in console
            s_bar = int((steer + 1.0) * 10)
            t_bar = int((throttle + 1.0) * 10)
            steer_vis = "[" + "#" * s_bar + " " * (20 - s_bar) + "]"
            throttle_vis = "[" + "#" * t_bar + " " * (20 - t_bar) + "]"

            # Format sensor distance string
            l_str = tof_dists["L"] or "--"
            c_str = tof_dists["C"] or "--"
            r_str = tof_dists["R"] or "--"
            tof_str = f"| ToF L:{l_str:>6} C:{c_str:>6} R:{r_str:>6}"

            line = f"\r{status_note} | S: {steer:+0.2f} {steer_vis} | T: {throttle:+0.2f} {throttle_vis} {tof_str} "
            sys.stdout.write(line.ljust(115))
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
                send_packet("0.0,0.0\n")
                send_packet("x\n")
                time.sleep(0.05)
            if ser:
                ser.close()
        except Exception:
            pass
        pygame.quit()
        print("Safely disconnected.")


if __name__ == "__main__":
    main()
