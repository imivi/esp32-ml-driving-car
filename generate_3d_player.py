#!/usr/bin/env python3
"""
generate_3d_player.py - Generate Standalone Three.js 3D Cockpit Simulation (Light Theme)

Reads track_data.csv and embeds the compact telemetry dataset into a self-contained
HTML/WebGL application powered by Three.js (docs/radar_3d.html):
- Light, clean engineering UI theme (#f8fafc background, crisp borders and shadows).
- Real Track Wall representations:
  * Realistic vertical solid barrier walls with red & white racing curb trim.
  * Continuous contour with depth/thickness that bends and moves based on sensor readings.
  * Front collision barrier if front sensor detects obstacles ahead.
  * Asphalt/concrete racetrack road surface with lane boundaries.
- RC car model anchored at the center with steerable wheels and telemetry indicators.
- Dynamic 3D laser beams (ToF Left 40°, Center 0°, Right -40°) with impact markers.
- Interactive camera controls (OrbitControls) + Inseguimento 3D, Top-Down 2D, Muso Auto presets.
- Full video player timeline (Play, Pause, Scrubber, Speed selector, Telemetry HUD).

Usage:
    python generate_3d_player.py --input track_data.csv --output docs/radar_3d.html
"""

import os
import sys
import json
import argparse
import pandas as pd


MAX_RANGE_MM = 1300


def build_3d_player(csv_path: str, output_path: str):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Telemetry CSV '{csv_path}' not found.")

    print(f"Reading telemetry from: {csv_path}...")
    df = pd.read_csv(csv_path)

    # Process and clamp sensor values
    for col in ["dist_left_mm", "dist_center_mm", "dist_right_mm"]:
        df[col] = df[col].apply(
            lambda x: (
                MAX_RANGE_MM
                if (pd.isna(x) or x <= 0 or x > MAX_RANGE_MM)
                else int(round(x))
            )
        )
    df["steer"] = df["steer"].fillna(0.0).round(3)
    df["direction"] = df["direction"].fillna("FORWARD")

    # Format: [dist_l, dist_c, dist_r, steer, direction]
    telemetry_list = df[
        ["dist_left_mm", "dist_center_mm", "dist_right_mm", "steer", "direction"]
    ].values.tolist()
    telemetry_json = json.dumps(telemetry_list)
    total_frames = len(telemetry_list)
    print(f"Processed {total_frames} frames ({len(telemetry_json)} bytes).")

    html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ESP32 RC Car - Simulatore 3D Tracciato & Radar</title>
  <!-- Three.js and OrbitControls via CDN -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      user-select: none;
    }}
    body {{
      background: #f1f5f9;
      color: #0f172a;
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
      overflow: hidden;
      width: 100vw;
      height: 100vh;
    }}
    #webgl-canvas {{
      width: 100%;
      height: 100%;
      display: block;
    }}

    /* Top Title HUD */
    .hud-top {{
      position: absolute;
      top: 18px;
      left: 24px;
      right: 24px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      pointer-events: none;
    }}
    .hud-title-box {{
      background: rgba(255, 255, 255, 0.92);
      border: 1.5px solid #cbd5e1;
      border-radius: 12px;
      padding: 12px 20px;
      backdrop-filter: blur(10px);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
      pointer-events: auto;
    }}
    .hud-title {{
      font-size: 16px;
      font-weight: 700;
      color: #1e3a8a;
      letter-spacing: 0.3px;
      margin-bottom: 2px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .hud-sub {{
      font-size: 12px;
      color: #64748b;
    }}

    /* View Presets */
    .hud-views {{
      display: flex;
      gap: 8px;
      pointer-events: auto;
    }}
    .btn-view {{
      background: rgba(255, 255, 255, 0.92);
      border: 1.5px solid #cbd5e1;
      color: #334155;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      backdrop-filter: blur(8px);
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      transition: all 0.15s ease;
    }}
    .btn-view:hover {{
      background: #eff6ff;
      color: #1d4ed8;
      border-color: #3b82f6;
    }}
    .btn-view.active {{
      background: #1e40af;
      color: #ffffff;
      border-color: #1e40af;
    }}

    /* Telemetry metrics widget */
    .telemetry-card {{
      position: absolute;
      left: 24px;
      bottom: 110px;
      background: rgba(255, 255, 255, 0.94);
      border: 1.5px solid #cbd5e1;
      border-radius: 12px;
      padding: 14px 18px;
      min-width: 240px;
      backdrop-filter: blur(10px);
      box-shadow: 0 6px 20px rgba(0,0,0,0.08);
      pointer-events: none;
      font-size: 13px;
      line-height: 1.6;
    }}
    .telemetry-card-title {{
      color: #475569;
      font-size: 11px;
      margin-bottom: 6px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 4px;
    }}
    .val-row {{
      display: flex;
      justify-content: space-between;
      font-family: monospace;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 2px;
    }}
    .val-left {{ color: #0284c7; }}
    .val-center {{ color: #16a34a; }}
    .val-right {{ color: #dc2626; }}
    .val-steer {{ color: #d97706; }}

    .hud-badge {{
      display: block;
      margin-top: 10px;
      padding: 6px 12px;
      border-radius: 6px;
      font-family: monospace;
      font-size: 13px;
      font-weight: 700;
      text-align: center;
      letter-spacing: 0.8px;
      background: #f0fdf4;
      border: 1.5px solid #86efac;
      color: #15803d;
      box-shadow: 0 2px 6px rgba(0,0,0,0.04);
      transition: all 0.2s ease;
    }}

    /* Bottom Control Bar */
    .player-controls {{
      position: absolute;
      bottom: 20px;
      left: 24px;
      right: 24px;
      background: rgba(255, 255, 255, 0.95);
      border: 1.5px solid #cbd5e1;
      border-radius: 14px;
      padding: 12px 22px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.1);
    }}
    .timeline-row {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .timeline-slider {{
      flex: 1;
      -webkit-appearance: none;
      height: 8px;
      border-radius: 4px;
      background: #e2e8f0;
      outline: none;
      cursor: pointer;
    }}
    .timeline-slider::-webkit-slider-thumb {{
      -webkit-appearance: none;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #2563eb;
      cursor: pointer;
      box-shadow: 0 2px 6px rgba(37, 99, 235, 0.5);
      transition: transform 0.1s;
    }}
    .timeline-slider::-webkit-slider-thumb:hover {{
      transform: scale(1.2);
    }}
    .time-label {{
      font-family: monospace;
      font-size: 13px;
      font-weight: 600;
      color: #475569;
      min-width: 95px;
      text-align: right;
    }}
    .buttons-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .btn-group {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .control-btn {{
      background: #ffffff;
      border: 1.5px solid #cbd5e1;
      color: #1e293b;
      padding: 7px 15px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      gap: 6px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .control-btn:hover {{
      background: #f8fafc;
      border-color: #94a3b8;
      color: #0f172a;
    }}
    .control-btn.active {{
      background: #2563eb;
      border-color: #2563eb;
      color: #ffffff;
    }}
    .speed-select {{
      background: #ffffff;
      border: 1.5px solid #cbd5e1;
      color: #1e293b;
      padding: 6px 10px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      outline: none;
      cursor: pointer;
    }}
  </style>
</head>
<body>

  <!-- WebGL Canvas Container -->
  <div id="webgl-canvas"></div>

  <!-- Top Title HUD -->
  <div class="hud-top">
    <div class="hud-title-box">
      <div class="hud-title">🚗 ESP32 RC Car • Simulatore Tracciato 3D</div>
      <div class="hud-sub">Visualizzazione egocentrica con pareti del tracciato dinamiche e telemetria ToF</div>
    </div>
    <div class="hud-views">
      <button id="btn-view-chase" class="btn-view active" onclick="setCameraView('chase')">Inseguimento 3D</button>
      <button id="btn-view-top" class="btn-view" onclick="setCameraView('top')">Vista Top-Down 2D</button>
      <button id="btn-view-front" class="btn-view" onclick="setCameraView('front')">Muso Auto</button>
    </div>
  </div>

  <!-- Telemetry HUD Card -->
  <div class="telemetry-card">
    <div class="telemetry-card-title">Telemetria Laser ToF</div>
    <div class="val-row"><span>Laser Sinistro (40°):</span> <span id="txt-left" class="val-left">--- mm</span></div>
    <div class="val-row"><span>Laser Centro (0°):</span>    <span id="txt-center" class="val-center">--- mm</span></div>
    <div class="val-row"><span>Laser Destro (-40°):</span>  <span id="txt-right" class="val-right">--- mm</span></div>
    <div class="val-row" style="margin-top: 6px; border-top: 1px dashed #e2e8f0; padding-top: 6px;">
      <span>Sterzo Joystick:</span> <span id="txt-steer" class="val-steer">0.00</span>
    </div>
    <span id="badge-direction" class="hud-badge">FORWARD</span>
  </div>

  <!-- Bottom Player Controls -->
  <div class="player-controls">
    <div class="timeline-row">
      <input type="range" id="timeline" class="timeline-slider" min="0" max="{total_frames - 1}" value="0">
      <div id="time-display" class="time-label">0.0s / 0.0s</div>
    </div>
    <div class="buttons-row">
      <div class="btn-group">
        <button id="btn-play" class="control-btn" onclick="togglePlay()">⏸ Pausa</button>
        <button class="control-btn" onclick="seekFrame(0)">⏮ Reset</button>
        <button class="control-btn" onclick="stepFrame(-1)">◀ Frame</button>
        <button class="control-btn" onclick="stepFrame(1)">Frame ▶</button>
      </div>
      <div class="btn-group">
        <label for="speed-select" style="font-size: 13px; color: #475569; font-weight: 600;">Velocità:</label>
        <select id="speed-select" class="speed-select" onchange="setSpeed(this.value)">
          <option value="0.5">0.5x</option>
          <option value="1.0" selected>1.0x (Tempo Reale)</option>
          <option value="1.5">1.5x</option>
          <option value="2.0">2.0x</option>
          <option value="3.0">3.0x</option>
        </select>
      </div>
    </div>
  </div>

  <script>
    // Embedded Telemetry Records: [dl, dc, dr, steer, direction]
    const telemetryData = {telemetry_json};
    const totalFrames = telemetryData.length;
    const samplingFps = 15.0; // 15 Hz telemetry recording

    // Three.js Core Objects
    let scene, camera, renderer, controls;
    let carGroup, frontLeftWheel, frontRightWheel, steerArrow;
    let beamLeft, beamCenter, beamRight;
    let impactLeft, impactCenter, impactRight;
    let wallCenterMesh, wallLeftMesh, wallRightMesh;
    let curbCenterMesh, curbLeftMesh, curbRightMesh;
    let trackAsphalt, trackGrid;

    // Playback state
    let isPlaying = true;
    let currentFrame = 0;
    let playbackSpeed = 1.0;
    let lastTimestamp = 0;
    let frameAccumulator = 0;

    // Sensor angles: Left = +40°, Center = 0°, Right = -40°
    const LEFT_ANGLE_RAD = (40.0 * Math.PI) / 180.0;
    const CENTER_ANGLE_RAD = 0.0;
    const RIGHT_ANGLE_RAD = (-40.0 * Math.PI) / 180.0;

    // Scaling: 1 unit in Three.js = 100 mm (0.1 meter)
    const SCALE = 0.01;

    // Track smoothing buffers for continuous realistic walls
    let smoothL = {{ x: -3.0, z: 2.0 }};
    let smoothC = {{ x:  0.0, z: 6.0 }};
    let smoothR = {{ x:  3.0, z: 2.0 }};

    function init3D() {{
      const container = document.getElementById('webgl-canvas');

      // 1. Scene & Light Background
      scene = new THREE.Scene();
      scene.background = new THREE.Color(0xf1f5f9); // Light slate
      scene.fog = new THREE.Fog(0xf1f5f9, 14, 32);

      camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 100);
      setCameraView('chase');

      // 2. Renderer with soft shadows
      renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false }});
      renderer.setPixelRatio(window.devicePixelRatio);
      renderer.setSize(window.innerWidth, window.innerHeight);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      container.appendChild(renderer.domElement);

      // 3. OrbitControls
      controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.06;
      controls.maxPolarAngle = Math.PI / 2 - 0.04; // Keep camera above road
      controls.target.set(0, 0.4, 1.6);

      // 4. Studio Lighting for Light Theme
      const hemiLight = new THREE.HemisphereLight(0xffffff, 0xe2e8f0, 0.85);
      hemiLight.position.set(0, 20, 0);
      scene.add(hemiLight);

      const sunLight = new THREE.DirectionalLight(0xffffff, 0.9);
      sunLight.position.set(8, 16, 6);
      sunLight.castShadow = true;
      sunLight.shadow.mapSize.width = 2048;
      sunLight.shadow.mapSize.height = 2048;
      sunLight.shadow.camera.near = 0.5;
      sunLight.shadow.camera.far = 30;
      sunLight.shadow.camera.left = -6;
      sunLight.shadow.camera.right = 6;
      sunLight.shadow.camera.top = 10;
      sunLight.shadow.camera.bottom = -4;
      sunLight.shadow.bias = -0.0005;
      scene.add(sunLight);

      // 5. Construct Environment & Track
      buildTrackSurface();
      buildRadarGrid();
      buildTrackWalls();
      buildCarModel();
      buildLaserBeams();

      window.addEventListener('resize', onWindowResize, false);
      requestAnimationFrame(animate);
    }}

    // Asphalt track road surface with moving motion stripes
    function buildTrackSurface() {{
      // Ground plane (infinite grey road)
      const roadGeo = new THREE.PlaneGeometry(30, 40);
      const roadMat = new THREE.MeshStandardMaterial({{
        color: 0xe2e8f0, // Light concrete / track surface
        roughness: 0.9,
        metalness: 0.05
      }});
      const road = new THREE.Mesh(roadGeo, roadMat);
      road.rotation.x = -Math.PI / 2;
      road.position.set(0, -0.01, 5);
      road.receiveShadow = true;
      scene.add(road);

      // Drivable lane surface (darker asphalt strip under car corridor)
      const asphaltGeo = new THREE.PlaneGeometry(8, 25);
      const asphaltMat = new THREE.MeshStandardMaterial({{
        color: 0xdbeafe, // Soft track tint
        roughness: 0.8,
      }});
      trackAsphalt = new THREE.Mesh(asphaltGeo, asphaltMat);
      trackAsphalt.rotation.x = -Math.PI / 2;
      trackAsphalt.position.set(0, 0.002, 6);
      trackAsphalt.receiveShadow = true;
      scene.add(trackAsphalt);
    }}

    // Clean Radar Distance Rings
    function buildRadarGrid() {{
      // Subtle distance rings: 300, 600, 900, 1200 mm
      [300, 600, 900, 1200].forEach(r_mm => {{
        const r = r_mm * SCALE;
        const ringGeo = new THREE.RingGeometry(r - 0.012, r + 0.012, 80);
        const ringMat = new THREE.MeshBasicMaterial({{
          color: 0x94a3b8,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.4
        }});
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(0, 0.005, 0);
        scene.add(ring);
      }});

      // Moving track center dashes to convey forward velocity
      trackGrid = new THREE.GridHelper(24, 24, 0x94a3b8, 0xcbd5e1);
      trackGrid.position.set(0, 0.006, 6);
      scene.add(trackGrid);
    }}

    // Helper to position and orient a 3D wall segment between two (X, Z) endpoints
    function setWallSegment(mesh, curbMesh, p1, p2, thickness = 0.25, height = 0.75) {{
      const dx = p2.x - p1.x;
      const dz = p2.z - p1.z;
      const len = Math.hypot(dx, dz);
      const angle = Math.atan2(dx, dz);

      // Midpoint
      const midX = (p1.x + p2.x) / 2;
      const midZ = (p1.z + p2.z) / 2;

      // Position Wall Barrier
      mesh.position.set(midX, height / 2, midZ);
      mesh.rotation.y = angle;
      mesh.scale.set(thickness, height, Math.max(0.01, len));

      // Position racing curb strip at base
      if (curbMesh) {{
        curbMesh.position.set(midX, 0.06, midZ);
        curbMesh.rotation.y = angle;
        curbMesh.scale.set(thickness + 0.2, 0.12, Math.max(0.01, len));
      }}
    }}

    // Construct realistic 3D Track Wall Barriers
    function buildTrackWalls() {{
      const wallMat = new THREE.MeshStandardMaterial({{
        color: 0xffffff,
        roughness: 0.45,
        metalness: 0.1,
      }});

      const curbMatCenter = new THREE.MeshStandardMaterial({{ color: 0x16a34a, roughness: 0.4 }}); // Green center curb
      const curbMatLeft   = new THREE.MeshStandardMaterial({{ color: 0x0284c7, roughness: 0.4 }}); // Blue left curb
      const curbMatRight  = new THREE.MeshStandardMaterial({{ color: 0xdc2626, roughness: 0.4 }}); // Red right curb

      // Base unit box geometries for walls (scaled and transformed dynamically)
      const unitWallGeo = new THREE.BoxGeometry(1, 1, 1);
      const unitCurbGeo = new THREE.BoxGeometry(1, 1, 1);

      // 1. Center wall at front detected point
      wallCenterMesh = new THREE.Mesh(unitWallGeo, wallMat);
      wallCenterMesh.castShadow = true;
      wallCenterMesh.receiveShadow = true;
      scene.add(wallCenterMesh);

      curbCenterMesh = new THREE.Mesh(unitCurbGeo, curbMatCenter);
      curbCenterMesh.receiveShadow = true;
      scene.add(curbCenterMesh);

      // 2. Left lateral wall (aligned along left side passing through left detected point)
      wallLeftMesh = new THREE.Mesh(unitWallGeo, wallMat);
      wallLeftMesh.castShadow = true;
      wallLeftMesh.receiveShadow = true;
      scene.add(wallLeftMesh);

      curbLeftMesh = new THREE.Mesh(unitCurbGeo, curbMatLeft);
      curbLeftMesh.receiveShadow = true;
      scene.add(curbLeftMesh);

      // 3. Right lateral wall (aligned along right side passing through right detected point)
      wallRightMesh = new THREE.Mesh(unitWallGeo, wallMat);
      wallRightMesh.castShadow = true;
      wallRightMesh.receiveShadow = true;
      scene.add(wallRightMesh);

      curbRightMesh = new THREE.Mesh(unitCurbGeo, curbMatRight);
      curbRightMesh.receiveShadow = true;
      scene.add(curbRightMesh);
    }}

    // Construct detailed RC Car 3D model
    function buildCarModel() {{
      carGroup = new THREE.Group();

      // Dimensions in Three.js units (160mm x 110mm)
      const carLength = 1.6;
      const carWidth = 1.1;
      const carHeight = 0.35;

      // Chassis Body (Deep Royal Blue)
      const bodyGeo = new THREE.BoxGeometry(carWidth, carHeight, carLength);
      const bodyMat = new THREE.MeshStandardMaterial({{
        color: 0x1e40af,
        roughness: 0.25,
        metalness: 0.6,
      }});
      const body = new THREE.Mesh(bodyGeo, bodyMat);
      body.position.y = 0.28;
      body.castShadow = true;
      body.receiveShadow = true;
      carGroup.add(body);

      // Electronics / Battery Pack
      const cabinGeo = new THREE.BoxGeometry(carWidth * 0.72, carHeight * 0.85, carLength * 0.55);
      const cabinMat = new THREE.MeshStandardMaterial({{
        color: 0x334155,
        roughness: 0.4,
        metalness: 0.5
      }});
      const cabin = new THREE.Mesh(cabinGeo, cabinMat);
      cabin.position.set(0, 0.44, -0.1);
      cabin.castShadow = true;
      carGroup.add(cabin);

      // ToF Sensor Bar Front Mount (Gold / Brass accent)
      const barGeo = new THREE.BoxGeometry(carWidth * 0.9, 0.08, 0.12);
      const barMat = new THREE.MeshStandardMaterial({{ color: 0x0284c7 }});
      const bar = new THREE.Mesh(barGeo, barMat);
      bar.position.set(0, 0.28, carLength / 2 + 0.06);
      carGroup.add(bar);

      // Wheels
      const wheelGeo = new THREE.CylinderGeometry(0.2, 0.2, 0.16, 24);
      wheelGeo.rotateZ(Math.PI / 2);
      const wheelMat = new THREE.MeshStandardMaterial({{ color: 0x1e293b, roughness: 0.8 }});

      // Rear wheels (fixed)
      const rearL = new THREE.Mesh(wheelGeo, wheelMat);
      rearL.position.set(-carWidth / 2 - 0.1, 0.2, -0.45);
      rearL.castShadow = true;
      carGroup.add(rearL);

      const rearR = new THREE.Mesh(wheelGeo, wheelMat);
      rearR.position.set(carWidth / 2 + 0.1, 0.2, -0.45);
      rearR.castShadow = true;
      carGroup.add(rearR);

      // Front wheels (steerable)
      frontLeftWheel = new THREE.Group();
      const fl = new THREE.Mesh(wheelGeo, wheelMat);
      fl.castShadow = true;
      frontLeftWheel.add(fl);
      frontLeftWheel.position.set(-carWidth / 2 - 0.1, 0.2, 0.45);
      carGroup.add(frontLeftWheel);

      frontRightWheel = new THREE.Group();
      const fr = new THREE.Mesh(wheelGeo, wheelMat);
      fr.castShadow = true;
      frontRightWheel.add(fr);
      frontRightWheel.position.set(carWidth / 2 + 0.1, 0.2, 0.45);
      carGroup.add(frontRightWheel);

      // Steering Direction Arrow on top of the car
      const arrowGeo = new THREE.ConeGeometry(0.12, 0.4, 16);
      arrowGeo.rotateX(Math.PI / 2);
      const arrowMat = new THREE.MeshStandardMaterial({{ color: 0x16a34a }});
      steerArrow = new THREE.Mesh(arrowGeo, arrowMat);
      steerArrow.position.set(0, 0.72, 0.55);
      carGroup.add(steerArrow);

      scene.add(carGroup);
    }}

    // Construct 3 dynamic laser rays + impact markers
    function buildLaserBeams() {{
      const createBeam = (colorHex) => {{
        const geo = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0, 0),
          new THREE.Vector3(0, 0, 1)
        ]);
        const mat = new THREE.LineBasicMaterial({{
          color: colorHex,
          linewidth: 3,
          transparent: true,
          opacity: 0.9
        }});
        const line = new THREE.Line(geo, mat);
        scene.add(line);
        return line;
      }};

      const createImpact = (colorHex) => {{
        const geo = new THREE.CylinderGeometry(0.08, 0.08, 0.75, 16);
        const mat = new THREE.MeshStandardMaterial({{
          color: colorHex,
          emissive: colorHex,
          emissiveIntensity: 0.3
        }});
        const cylinder = new THREE.Mesh(geo, mat);
        cylinder.position.y = 0.375;
        scene.add(cylinder);
        return cylinder;
      }};

      beamLeft = createBeam(0x0284c7);    // Blue Left
      beamCenter = createBeam(0x16a34a);  // Green Center
      beamRight = createBeam(0xdc2626);   // Red Right

      impactLeft = createImpact(0x0284c7);
      impactCenter = createImpact(0x16a34a);
      impactRight = createImpact(0xdc2626);
    }}

    // Update scene state based on telemetry frame
    function updateFrame(frameIndex) {{
      const row = telemetryData[frameIndex];
      const dl_mm = row[0];
      const dc_mm = row[1];
      const dr_mm = row[2];
      const steer = row[3];
      const direction = row[4];

      // Convert mm to 3D coordinates (Forward = +Z, Right = +X, Left = -X)
      const origin = new THREE.Vector3(0, 0.28, 0.86);

      const targetL = new THREE.Vector3(
        -dl_mm * SCALE * Math.sin(LEFT_ANGLE_RAD),
        0.28,
        origin.z + dl_mm * SCALE * Math.cos(LEFT_ANGLE_RAD)
      );

      const targetC = new THREE.Vector3(
        0,
        0.28,
        origin.z + dc_mm * SCALE * Math.cos(CENTER_ANGLE_RAD)
      );

      const targetR = new THREE.Vector3(
        -dr_mm * SCALE * Math.sin(RIGHT_ANGLE_RAD), // -(-angle) = +X (right)
        0.28,
        origin.z + dr_mm * SCALE * Math.cos(RIGHT_ANGLE_RAD)
      );

      // Smooth interpolation for walls to avoid jerky visual jumps
      const lerpFactor = 0.35;
      smoothL.x += (targetL.x - smoothL.x) * lerpFactor;
      smoothL.z += (targetL.z - smoothL.z) * lerpFactor;

      smoothC.x += (targetC.x - smoothC.x) * lerpFactor;
      smoothC.z += (targetC.z - smoothC.z) * lerpFactor;

      smoothR.x += (targetR.x - smoothR.x) * lerpFactor;
      smoothR.z += (targetR.z - smoothR.z) * lerpFactor;

      // 1. Update Laser Beams geometry
      beamLeft.geometry.setFromPoints([origin, targetL]);
      beamCenter.geometry.setFromPoints([origin, targetC]);
      beamRight.geometry.setFromPoints([origin, targetR]);

      impactLeft.position.set(targetL.x, 0.375, targetL.z);
      impactCenter.position.set(targetC.x, 0.375, targetC.z);
      impactRight.position.set(targetR.x, 0.375, targetR.z);

      // 2. Track Walls Setup (Center wall + Left wall + Right wall, unlinked):
      // A. Center Wall centered at front detected point (smoothC.x, smoothC.z)
      const centerHalfWidth = 1.0;
      const pCenterL = {{ x: smoothC.x - centerHalfWidth, z: smoothC.z }};
      const pCenterR = {{ x: smoothC.x + centerHalfWidth, z: smoothC.z }};
      setWallSegment(wallCenterMesh, curbCenterMesh, pCenterL, pCenterR, 0.25, 0.75);

      // B. Left Lateral Wall: starts from the rear and ends exactly on the left detected point (smoothL)
      const wallBackLength = 4.0;
      const pLeftFront = {{ x: smoothL.x, z: smoothL.z }};
      const pLeftBack  = {{ x: smoothL.x - 0.2, z: smoothL.z - wallBackLength }};
      setWallSegment(wallLeftMesh, curbLeftMesh, pLeftBack, pLeftFront, 0.25, 0.75);

      // C. Right Lateral Wall: starts from the rear and ends exactly on the right detected point (smoothR)
      const pRightFront = {{ x: smoothR.x, z: smoothR.z }};
      const pRightBack  = {{ x: smoothR.x + 0.2, z: smoothR.z - wallBackLength }};
      setWallSegment(wallRightMesh, curbRightMesh, pRightBack, pRightFront, 0.25, 0.75);

      // 3. Front wheels steering rotation (steer: -1.0 left to +1.0 right)
      const wheelSteerAngle = -steer * 0.42; // radians (~24 deg)
      frontLeftWheel.rotation.y = wheelSteerAngle;
      frontRightWheel.rotation.y = wheelSteerAngle;
      steerArrow.rotation.y = wheelSteerAngle;

      // 4. Update UI HUD elements
      document.getElementById('txt-left').textContent = `${{dl_mm}} mm`;
      document.getElementById('txt-center').textContent = `${{dc_mm}} mm`;
      document.getElementById('txt-right').textContent = `${{dr_mm}} mm`;
      document.getElementById('txt-steer').textContent = steer >= 0 ? `+${{steer.toFixed(2)}}` : steer.toFixed(2);

      const badge = document.getElementById('badge-direction');
      badge.textContent = direction;
      if (direction === 'FORWARD') {{
        badge.style.background = '#f0fdf4';
        badge.style.borderColor = '#86efac';
        badge.style.color = '#15803d';
        steerArrow.material.color.setHex(0x16a34a);
      }} else if (direction === 'FORWARD_LEFT') {{
        badge.style.background = '#eff6ff';
        badge.style.borderColor = '#93c5fd';
        badge.style.color = '#1d4ed8';
        steerArrow.material.color.setHex(0x0284c7);
      }} else {{
        badge.style.background = '#fef2f2';
        badge.style.borderColor = '#fca5a5';
        badge.style.color = '#b91c1c';
        steerArrow.material.color.setHex(0xdc2626);
      }}

      // Timeline & time label
      document.getElementById('timeline').value = frameIndex;
      const elapsedSec = (frameIndex / samplingFps).toFixed(1);
      const totalSec = (totalFrames / samplingFps).toFixed(1);
      document.getElementById('time-display').textContent = `${{elapsedSec}}s / ${{totalSec}}s`;
    }}

    // Animation & Playback Loop
    function animate(timestamp) {{
      requestAnimationFrame(animate);

      if (!lastTimestamp) lastTimestamp = timestamp;
      const deltaSec = (timestamp - lastTimestamp) / 1000.0;
      lastTimestamp = timestamp;

      if (isPlaying) {{
        frameAccumulator += deltaSec * samplingFps * playbackSpeed;
        const framesToAdvance = Math.floor(frameAccumulator);
        if (framesToAdvance > 0) {{
          currentFrame = (currentFrame + framesToAdvance) % totalFrames;
          frameAccumulator -= framesToAdvance;
          updateFrame(currentFrame);
        }}

        // Simulated floor motion
        if (trackGrid) {{
          trackGrid.position.z = ((trackGrid.position.z - deltaSec * 3.5 * playbackSpeed) % 1.0) + 6.0;
        }}
      }}

      controls.update();
      renderer.render(scene, camera);
    }}

    // UI Interactive Functions
    function togglePlay() {{
      isPlaying = !isPlaying;
      const btn = document.getElementById('btn-play');
      btn.textContent = isPlaying ? '⏸ Pausa' : '▶ Play';
      btn.classList.toggle('active', !isPlaying);
    }}

    function seekFrame(idx) {{
      currentFrame = Math.max(0, Math.min(totalFrames - 1, idx));
      frameAccumulator = 0;
      updateFrame(currentFrame);
    }}

    function stepFrame(delta) {{
      seekFrame(currentFrame + delta);
    }}

    function setSpeed(val) {{
      playbackSpeed = parseFloat(val);
    }}

    document.getElementById('timeline').addEventListener('input', function(e) {{
      seekFrame(parseInt(e.target.value));
    }});

    // Camera Preset Views
    function setCameraView(preset) {{
      document.querySelectorAll('.btn-view').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.getElementById('btn-view-' + preset);
      if (activeBtn) activeBtn.classList.add('active');

      if (preset === 'chase') {{
        // Behind and slightly above looking forward
        camera.position.set(0, 3.2, -3.2);
        if (controls) controls.target.set(0, 0.4, 2.2);
      }} else if (preset === 'top') {{
        // Pure top-down 2D radar view
        camera.position.set(0, 9.2, 1.6);
        if (controls) controls.target.set(0, 0, 1.6);
      }} else if (preset === 'front') {{
        // First-person bumper viewpoint
        camera.position.set(0, 0.75, 0.9);
        if (controls) controls.target.set(0, 0.5, 5.0);
      }}
    }}

    function onWindowResize() {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }}

    // Boot
    window.onload = () => {{
      init3D();
      updateFrame(0);
    }};
  </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Standalone 3D Player successfully generated at: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate 3D WebGL Ego-Centric Radar Player from Telemetry"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="track_data.csv",
        help="Input CSV (default: track_data.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/radar_3d.html",
        help="Output HTML (default: docs/radar_3d.html)",
    )
    args = parser.parse_args()

    try:
        build_3d_player(args.input, args.output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
