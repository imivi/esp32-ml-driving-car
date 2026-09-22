#!/usr/bin/env python3
"""
render_cockpit_video.py - Render Ego-Centric Radar Video of RC Car Telemetry

Renders a dynamic top-down cockpit simulation where:
1. The RC car remains fixed at the center oriented upward (Y-axis forward).
2. The 3 laser ToF beams sweep dynamically according to distance readings.
3. Wall boundaries are fitted and drawn around the car.
4. Dashboard instruments show real-time steering angle, direction label, and distances.
5. Exports directly to MP4 (via matplotlib animation / ffmpeg) or interactive player.

Usage:
    python render_cockpit_video.py --output docs/cockpit_replay.mp4 --fps 20
    python render_cockpit_video.py --preview --max-frames 200
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, FancyArrowPatch, Wedge
from matplotlib.animation import FuncAnimation, FFMpegWriter

# Vehicle dimensions (in mm)
CAR_LENGTH_MM = 160
CAR_WIDTH_MM = 110
WHEEL_LENGTH_MM = 45
WHEEL_WIDTH_MM = 18

# Sensor angles relative to vehicle forward heading (+Y = 0 rad, Left = +40 deg, Right = -40 deg)
LEFT_ANGLE_DEG = 40.0
CENTER_ANGLE_DEG = 0.0
RIGHT_ANGLE_DEG = -40.0

# Max sensor range for visualization clipping (mm)
MAX_RANGE_MM = 1300.0


def load_telemetry(csv_path: str):
    """Loads and cleans track_data.csv."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"File '{csv_path}' not found.")

    df = pd.read_csv(csv_path)

    # Filter out invalid / negative readings (replace -1 with MAX_RANGE_MM)
    for col in ["dist_left_mm", "dist_center_mm", "dist_right_mm"]:
        df[col] = df[col].apply(
            lambda x: (
                MAX_RANGE_MM if (pd.isna(x) or x <= 0 or x > MAX_RANGE_MM) else float(x)
            )
        )

    df["steer"] = df["steer"].fillna(0.0).clip(-1.0, 1.0)
    df["direction"] = df["direction"].fillna("FORWARD")
    return df


def sensor_to_cartesian(dist_mm: float, angle_deg: float):
    """Converts sensor polar reading to egocentric Cartesian coordinates (X right, Y forward)."""
    # Angle 0 deg = +Y, +40 deg = left (-X, +Y), -40 deg = right (+X, +Y)
    rad = np.radians(angle_deg)
    x = -dist_mm * np.sin(rad)
    y = dist_mm * np.cos(rad)
    return x, y


def setup_figure():
    """Sets up the dark-themed cockpit radar canvas."""
    fig = plt.figure(figsize=(10, 10), facecolor="#090d16")
    ax = fig.add_axes([0.05, 0.05, 0.90, 0.90])
    ax.set_facecolor("#0d1321")

    # Set coordinate limits around the car (vehicle at origin x=0, y=0)
    ax.set_xlim(-850, 850)
    ax.set_ylim(-350, 1350)
    ax.set_aspect("equal")
    ax.axis("off")

    return fig, ax


def draw_static_radar_grid(ax):
    """Draws distance radar concentric arcs and guideline circles."""
    theta = np.linspace(np.radians(-75), np.radians(75), 100)
    for r in [300, 600, 900, 1200]:
        xs = -r * np.sin(theta)
        ys = r * np.cos(theta)
        ax.plot(xs, ys, color="#1e293b", linestyle="--", linewidth=1, zorder=1)
        ax.text(
            15,
            r + 15,
            f"{r} mm",
            color="#475569",
            fontsize=8,
            fontfamily="monospace",
            zorder=1,
        )

    # Guidelines for the 3 sensor beam directions
    for angle, label in [
        (LEFT_ANGLE_DEG, "40° SX"),
        (CENTER_ANGLE_DEG, "0°"),
        (RIGHT_ANGLE_DEG, "40° DX"),
    ]:
        bx, by = sensor_to_cartesian(MAX_RANGE_MM * 0.98, angle)
        ax.plot(
            [0, bx], [0, by], color="#1e293b", linestyle=":", linewidth=0.8, zorder=1
        )


def draw_vehicle_body(ax):
    """Draws the fixed RC car chassis at the center."""
    # Main chassis rectangle
    chassis = Rectangle(
        (-CAR_WIDTH_MM / 2, -CAR_LENGTH_MM / 2),
        CAR_WIDTH_MM,
        CAR_LENGTH_MM,
        facecolor="#1e3a8a",
        edgecolor="#38bdf8",
        linewidth=2,
        zorder=6,
        alpha=0.95,
    )
    ax.add_patch(chassis)

    # Windshield / Front indicator triangle
    front_marker = Polygon(
        [
            [-CAR_WIDTH_MM * 0.35, CAR_LENGTH_MM * 0.25],
            [CAR_WIDTH_MM * 0.35, CAR_LENGTH_MM * 0.25],
            [0, CAR_LENGTH_MM * 0.48],
        ],
        facecolor="#0284c7",
        edgecolor="#7dd3fc",
        linewidth=1,
        zorder=7,
    )
    ax.add_patch(front_marker)

    # Wheels (fixed rear wheels, animated front wheels handled separately)
    # Rear Left
    ax.add_patch(
        Rectangle(
            (-CAR_WIDTH_MM / 2 - WHEEL_WIDTH_MM - 2, -CAR_LENGTH_MM / 2 + 10),
            WHEEL_WIDTH_MM,
            WHEEL_LENGTH_MM,
            facecolor="#334155",
            edgecolor="#64748b",
            zorder=5,
        )
    )
    # Rear Right
    ax.add_patch(
        Rectangle(
            (CAR_WIDTH_MM / 2 + 2, -CAR_LENGTH_MM / 2 + 10),
            WHEEL_WIDTH_MM,
            WHEEL_LENGTH_MM,
            facecolor="#334155",
            edgecolor="#64748b",
            zorder=5,
        )
    )


def create_animation(
    df: pd.DataFrame,
    output_path: str | None = None,
    fps: int = 15,
    max_frames: int | None = None,
):
    """Generates the ego-centric animation sequence."""
    if max_frames and max_frames > 0:
        df = df.iloc[:max_frames].copy().reset_index(drop=True)

    fig, ax = setup_figure()
    draw_static_radar_grid(ax)
    draw_vehicle_body(ax)

    # Dynamic graphical elements
    # 1. Laser sensor rays
    (line_l,) = ax.plot([], [], color="#38bdf8", linewidth=2.5, zorder=3, alpha=0.9)
    (line_c,) = ax.plot([], [], color="#4ade80", linewidth=2.5, zorder=3, alpha=0.9)
    (line_r,) = ax.plot([], [], color="#f87171", linewidth=2.5, zorder=3, alpha=0.9)

    # 2. Laser impact points
    (point_l,) = ax.plot(
        [], [], "o", color="#38bdf8", markersize=9, markeredgecolor="#ffffff", zorder=4
    )
    (point_c,) = ax.plot(
        [], [], "o", color="#4ade80", markersize=9, markeredgecolor="#ffffff", zorder=4
    )
    (point_r,) = ax.plot(
        [], [], "o", color="#f87171", markersize=9, markeredgecolor="#ffffff", zorder=4
    )

    # 3. Dynamic track corridor boundary
    (wall_left_line,) = ax.plot(
        [], [], color="#38bdf8", linewidth=3, linestyle="-", alpha=0.7, zorder=2
    )
    (wall_right_line,) = ax.plot(
        [], [], color="#f87171", linewidth=3, linestyle="-", alpha=0.7, zorder=2
    )
    track_front_poly = Polygon(
        [[0, 0], [0, 0], [0, 0]], facecolor="#1e293b", alpha=0.25, zorder=2
    )
    ax.add_patch(track_front_poly)

    # 4. Steering vector arrow
    steer_arrow = FancyArrowPatch(
        (0, 0),
        (0, 0),
        color="#fbbf24",
        arrowstyle="-|>",
        mutation_scale=20,
        linewidth=3.5,
        zorder=8,
    )
    ax.add_patch(steer_arrow)

    # 5. Dashboard text overlays
    title_text = ax.text(
        -800,
        1260,
        "ESP32 RC CAR - EGO-RADAR COCKPIT",
        color="#f8fafc",
        fontsize=14,
        fontweight="bold",
        fontfamily="sans-serif",
        zorder=10,
    )
    stats_text = ax.text(
        -800, 1140, "", color="#94a3b8", fontsize=10, fontfamily="monospace", zorder=10
    )
    decision_badge = ax.text(
        550,
        1240,
        "",
        color="#ffffff",
        fontsize=12,
        fontweight="bold",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#1e293b", edgecolor="#475569"),
        zorder=10,
    )

    # History buffer for corridor smoothing
    history_l = []
    history_r = []
    max_history = 6

    def init():
        line_l.set_data([], [])
        line_c.set_data([], [])
        line_r.set_data([], [])
        point_l.set_data([], [])
        point_c.set_data([], [])
        point_r.set_data([], [])
        wall_left_line.set_data([], [])
        wall_right_line.set_data([], [])
        return (
            line_l,
            line_c,
            line_r,
            point_l,
            point_c,
            point_r,
            wall_left_line,
            wall_right_line,
        )

    def update(frame_idx):
        row = df.iloc[frame_idx]
        dl = row["dist_left_mm"]
        dc = row["dist_center_mm"]
        dr = row["dist_right_mm"]
        steer = row["steer"]
        direction = row["direction"]

        # Calculate Cartesian endpoints for the 3 sensors from car front bumper (0, CAR_LENGTH_MM/2)
        origin_y = CAR_LENGTH_MM / 2
        xl, yl = sensor_to_cartesian(dl, LEFT_ANGLE_DEG)
        xc, yc = sensor_to_cartesian(dc, CENTER_ANGLE_DEG)
        xr, yr = sensor_to_cartesian(dr, RIGHT_ANGLE_DEG)

        yl += origin_y
        yc += origin_y
        yr += origin_y

        # Update sensor beams
        line_l.set_data([0, xl], [origin_y, yl])
        line_c.set_data([0, xc], [origin_y, yc])
        line_r.set_data([0, xr], [origin_y, yr])

        point_l.set_data([xl], [yl])
        point_c.set_data([xc], [yc])
        point_r.set_data([xr], [yr])

        # Track contour estimation:
        # Left wall segment passing near (xl, yl), Right wall segment passing near (xr, yr)
        # We project wall tangents aligned with track corridor
        wall_span = 250
        wall_left_line.set_data(
            [xl + 40, xl, xl - 50], [yl - wall_span, yl, yl + wall_span]
        )
        wall_right_line.set_data(
            [xr - 40, xr, xr + 50], [yr - wall_span, yr, yr + wall_span]
        )

        # Update corridor polygon
        track_front_poly.set_xy(
            [
                [xl, yl],
                [xc, yc],
                [xr, yr],
                [CAR_WIDTH_MM / 2, origin_y],
                [-CAR_WIDTH_MM / 2, origin_y],
            ]
        )

        # Steering arrow from center of car forward/angled
        arrow_len = 160
        # Steer: -1 (left) to +1 (right) -> map to angle
        steer_angle_rad = np.radians(
            -steer * 45.0
        )  # negative steer in dataset turns left
        ax_tip = arrow_len * np.sin(steer_angle_rad)
        ay_tip = origin_y + arrow_len * np.cos(steer_angle_rad)
        steer_arrow.set_positions((0, origin_y), (ax_tip, ay_tip))

        # Color-code steer arrow
        if direction == "FORWARD":
            steer_arrow.set_color("#22c55e")
            decision_badge.set_text("▲ FORWARD")
            decision_badge.get_bbox_patch().set_facecolor("#14532d")
            decision_badge.get_bbox_patch().set_edgecolor("#22c55e")
        elif direction == "FORWARD_LEFT":
            steer_arrow.set_color("#38bdf8")
            decision_badge.set_text("◄ FORWARD_LEFT")
            decision_badge.get_bbox_patch().set_facecolor("#0c4a6e")
            decision_badge.get_bbox_patch().set_edgecolor("#38bdf8")
        else:
            steer_arrow.set_color("#f87171")
            decision_badge.set_text("► FORWARD_RIGHT")
            decision_badge.get_bbox_patch().set_facecolor("#7f1d1d")
            decision_badge.get_bbox_patch().set_edgecolor("#f87171")

        # Telemetry metrics overlay
        time_elapsed = frame_idx / fps
        stats_str = (
            f"Frame: {frame_idx:04d} / {len(df):04d}  |  Time: {time_elapsed:5.1f}s\n"
            f"ToF SX: {dl:4.0f} mm  |  Centro: {dc:4.0f} mm  |  DX: {dr:4.0f} mm\n"
            f"Sterzo: {steer:+.2f}  |  Delta (SX-DX): {dl - dr:+4.0f} mm"
        )
        stats_text.set_text(stats_str)

        return (
            line_l,
            line_c,
            line_r,
            point_l,
            point_c,
            point_r,
            wall_left_line,
            wall_right_line,
            track_front_poly,
            steer_arrow,
            stats_text,
            decision_badge,
        )

    anim = FuncAnimation(
        fig, update, init_func=init, frames=len(df), interval=1000.0 / fps, blit=False
    )

    if output_path:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        print(f"Rendering {len(df)} frames to video: {output_path} (FPS={fps})...")
        writer = FFMpegWriter(
            fps=fps, metadata=dict(artist="Antigravity"), bitrate=2400
        )
        anim.save(output_path, writer=writer)
        print(f"Video export complete: {output_path}")
    else:
        plt.show()

    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Render ego-centric cockpit radar video of RC car telemetry"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="track_data.csv",
        help="Path to telemetry CSV (default: track_data.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/cockpit_radar.mp4",
        help="Output video file path (.mp4) (default: docs/cockpit_radar.mp4)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=15,
        help="Framerate of animation (default: 15 fps, matching sensor sampling rate)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Render up to N frames (useful for quick previews or test clips)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Open interactive preview window instead of saving to MP4",
    )
    args = parser.parse_args()

    try:
        print(f"Loading telemetry from {args.data}...")
        df = load_telemetry(args.data)
        print(f"Loaded {len(df)} rows.")

        if args.preview:
            create_animation(
                df, output_path=None, fps=args.fps, max_frames=args.max_frames
            )
        else:
            create_animation(
                df, output_path=args.output, fps=args.fps, max_frames=args.max_frames
            )

    except Exception as e:
        print(f"Error during video generation: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
