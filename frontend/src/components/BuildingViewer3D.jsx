import React, { useState, useMemo, useEffect, useRef } from 'react'
import * as THREE from 'three'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, Html, GizmoHelper, GizmoViewport } from '@react-three/drei'
import { Maximize2, Minimize2, Compass, Ruler, Navigation, Eye } from 'lucide-react'


const roomColors = {
  "Entrance": "#a6adc8",       // Cool Slate
  "Living Room": "#818cf8",     // Soft Indigo
  "Kitchen": "#fbbf24",         // Warm Gold
  "Bedroom": "#4ade80",         // Soft Leaf Green
  "Bathroom": "#f472b6",        // Soft Rose
  "Corridor": "#2dd4bf",        // Soft Teal
  "OTS": "#38bdf8",             // Sky Blue (open shafts)
  "Staircase": "#f59e0b",       // Amber
}

class CanvasErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  componentDidCatch(error, errorInfo) {
    console.error("Canvas 3D Error caught by Boundary:", error, errorInfo)
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-6 text-center bg-[#07070a] text-slate-300 font-mono">
          <div className="text-amber-400 font-semibold mb-2">3D Viewport Notice</div>
          <div className="text-xs text-slate-400 max-w-md">
            Rendering fallback active. You can switch to the 2D CAD Blueprint view for full structural plans.
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded border border-slate-700 cursor-pointer"
          >
            Retry 3D Rendering
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// Helper to determine if an opening is hosted by a wall segment
function getOpeningsOnWall(wall, openings, tolerance = 0.5) {
  const [x1, y1] = wall.start
  const [x2, y2] = wall.end
  const dx = x2 - x1
  const dy = y2 - y1
  const wallLength = Math.sqrt(dx * dx + dy * dy)
  if (wallLength < 0.1) return []

  const ux = dx / wallLength
  const uy = dy / wallLength

  const hosted = []
  openings.forEach(op => {
    const [ox, oy] = op.position

    // Project opening point onto wall line
    const tx = ox - x1
    const ty = oy - y1
    const projDist = tx * ux + ty * uy

    if (projDist >= -tolerance && projDist <= wallLength + tolerance) {
      // Calculate perpendicular distance to wall
      const perpDist = Math.abs(tx * (-uy) + ty * ux)
      if (perpDist <= tolerance) {
        hosted.push({
          ...op,
          distAlongWall: Math.max(0, Math.min(projDist, wallLength))
        })
      }
    }
  })

  // Sort openings along the wall from start to end
  return hosted.sort((a, b) => a.distAlongWall - b.distAlongWall)
}

// 3D Door Model
function ProceduralDoor3D({ position, direction, width, height = 7.0 }) {
  const angle = direction === "vertical" ? Math.PI / 2 : 0

  return (
    <group position={position} rotation={[0, angle, 0]}>
      {/* Wooden Door Frame */}
      <mesh position={[-width / 2 + 0.05, height / 2, 0]}>
        <boxGeometry args={[0.1, height, 0.15]} />
        <meshStandardMaterial color="#4e3629" roughness={0.7} />
      </mesh>
      <mesh position={[width / 2 - 0.05, height / 2, 0]}>
        <boxGeometry args={[0.1, height, 0.15]} />
        <meshStandardMaterial color="#4e3629" roughness={0.7} />
      </mesh>
      <mesh position={[0, height - 0.05, 0]}>
        <boxGeometry args={[width, 0.1, 0.15]} />
        <meshStandardMaterial color="#4e3629" roughness={0.7} />
      </mesh>

      {/* Door Leaf (Hinged at left side, rotated open 35 degrees) */}
      <group position={[-width / 2 + 0.1, 0, 0]} rotation={[0, -Math.PI / 5, 0]}>
        <mesh position={[(width - 0.2) / 2, height / 2, 0]}>
          <boxGeometry args={[width - 0.2, height - 0.15, 0.05]} />
          <meshStandardMaterial color="#a0522d" roughness={0.5} metalness={0.1} />
        </mesh>
        {/* Doorknob */}
        <mesh position={[width - 0.35, height / 2, 0.05]}>
          <sphereGeometry args={[0.04, 8, 8]} />
          <meshStandardMaterial color="#ffd700" metalness={0.8} roughness={0.2} />
        </mesh>
      </group>
    </group>
  )
}

// 3D Window Model
function ProceduralWindow3D({ position, direction, width, height = 4.0, sillHeight = 3.0 }) {
  const angle = direction === "vertical" ? Math.PI / 2 : 0

  return (
    <group position={[position[0], position[1] + sillHeight + height / 2, position[2]]} rotation={[0, angle, 0]}>
      {/* Aluminium Outer Frame */}
      <mesh>
        <boxGeometry args={[width, height, 0.15]} />
        <meshStandardMaterial color="#334155" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* Glass Pane */}
      <mesh>
        <boxGeometry args={[width - 0.1, height - 0.1, 0.02]} />
        <meshPhysicalMaterial
          color="#38bdf8"
          transmission={0.9}
          opacity={0.3}
          transparent
          roughness={0.1}
          ior={1.5}
        />
      </mesh>
      {/* Center Mullion */}
      <mesh>
        <boxGeometry args={[0.04, height, 0.16]} />
        <meshStandardMaterial color="#1e293b" metalness={0.7} roughness={0.3} />
      </mesh>
    </group>
  )
}

// 3D Stairs Step by Step (Highlighted Vertical Circulation Core)
function ProceduralStairs3D({ rect, floorHeight = 10.0, baseZ = 0 }) {
  const stepCount = 16
  const stepHeight = floorHeight / stepCount
  const landingDepth = Math.min(3.0, rect.h * 0.35)
  const runDepth = rect.h - landingDepth
  const stepDepth = runDepth / (stepCount / 2)
  const flightWidth = Math.max(1.0, rect.w / 2 - 0.2)

  const steps = []

  // Flight 1: Going Up (Bottom-Left to Landing)
  for (let i = 0; i < stepCount / 2; i++) {
    const y = baseZ + i * stepHeight + stepHeight / 2
    const z = rect.y + i * stepDepth + stepDepth / 2
    const x = rect.x + flightWidth / 2

    steps.push(
      <mesh key={`flight1-step-${i}`} position={[x, y, z]}>
        <boxGeometry args={[flightWidth, stepHeight, stepDepth]} />
        <meshStandardMaterial color="#f59e0b" roughness={0.4} metalness={0.1} />
      </mesh>
    )
  }

  // Mid-Landing
  const landingY = baseZ + (stepCount / 2) * stepHeight - stepHeight / 2
  const landingZ = rect.y + runDepth + landingDepth / 2
  steps.push(
    <mesh key="mid-landing" position={[rect.x + rect.w / 2, landingY, landingZ]}>
      <boxGeometry args={[rect.w, stepHeight, landingDepth]} />
      <meshStandardMaterial color="#d97706" roughness={0.4} metalness={0.15} />
    </mesh>
  )

  // Flight 2: Going Up to Next Floor (Landing to Top-Right)
  for (let i = 0; i < stepCount / 2; i++) {
    const y = baseZ + (stepCount / 2 + i) * stepHeight + stepHeight / 2
    const z = rect.y + runDepth - (i + 1) * stepDepth + stepDepth / 2
    const x = rect.x + rect.w - flightWidth / 2

    steps.push(
      <mesh key={`flight2-step-${i}`} position={[x, y, z]}>
        <boxGeometry args={[flightWidth, stepHeight, stepDepth]} />
        <meshStandardMaterial color="#f59e0b" roughness={0.4} metalness={0.1} />
      </mesh>
    )
  }

  return <group>{steps}</group>
}


// 3D Constructive Wall with precise boolean cutouts & architectural transparency
function ProceduralWall3D({
  wall,
  openings,
  floorHeight = 10.0,
  baseZ = 0,
  plotWidth,
  plotDepth,
  isAllFloorsView = false,
}) {
  const [x1, y1] = wall.start
  const [x2, y2] = wall.end
  const dx = x2 - x1
  const dy = y2 - y1
  const length = Math.sqrt(dx * dx + dy * dy)
  if (length < 0.1) return null

  const ux = dx / length
  const uy = dy / length
  const angle = Math.atan2(dy, dx)

  const thickness = wall.thickness || 0.5
  const isExterior = wall.type === "exterior"

  // Material tuning for architectural readability:
  // In All Floors view: exterior walls are ghosted (semi-transparent) so interior rooms/doors/stairs are readable.
  // Interior partition walls remain solid and crisp.
  const wallMatProps = isExterior
    ? (isAllFloorsView
      ? { color: "#94a3b8", transparent: true, opacity: 0.28, roughness: 0.4 }
      : { color: "#cbd5e1", transparent: true, opacity: 0.70, roughness: 0.6 })
    : { color: "#f8fafc", transparent: true, opacity: 0.92, roughness: 0.7 }

  // Query opening list lying on this wall line
  const hostedOpenings = getOpeningsOnWall(wall, openings)

  // Build panels
  const panels = []
  let currentD = 0

  hostedOpenings.forEach((op, opIdx) => {
    const opW = op.width
    const opStart = op.distAlongWall - opW / 2
    const opEnd = op.distAlongWall + opW / 2

    // 1. Solid wall panel before the opening
    if (opStart > currentD + 0.05) {
      const panelL = opStart - currentD
      const midD = currentD + panelL / 2
      const cx = x1 + midD * ux
      const cy = baseZ + floorHeight / 2
      const cz = y1 + midD * uy

      panels.push(
        <mesh
          key={`wall-${wall.id}-panel-pre-${opIdx}`}
          position={[cx - plotWidth / 2, cy, cz - plotDepth / 2]}
          rotation={[0, -angle, 0]}
        >
          <boxGeometry args={[panelL, floorHeight, thickness]} />
          <meshStandardMaterial {...wallMatProps} />
        </mesh>
      )
    }

    // 2. Transverse segments (Header / Sill) over the opening span
    const midOpD = op.distAlongWall
    const cx = x1 + midOpD * ux
    const cz = y1 + midOpD * uy

    if (op.type === "door") {
      // Header panel above door
      const headerHeight = floorHeight - 7.0
      if (headerHeight > 0.05) {
        const cy = baseZ + 7.0 + headerHeight / 2
        panels.push(
          <mesh
            key={`wall-${wall.id}-door-header-${opIdx}`}
            position={[cx - plotWidth / 2, cy, cz - plotDepth / 2]}
            rotation={[0, -angle, 0]}
          >
            <boxGeometry args={[opW, headerHeight, thickness]} />
            <meshStandardMaterial {...wallMatProps} />
          </mesh>
        )
      }
    } else {
      // Window Sill (0 to 3 ft)
      const sillH = 3.0
      const cySill = baseZ + sillH / 2
      panels.push(
        <mesh
          key={`wall-${wall.id}-win-sill-${opIdx}`}
          position={[cx - plotWidth / 2, cySill, cz - plotDepth / 2]}
          rotation={[0, -angle, 0]}
        >
          <boxGeometry args={[opW, sillH, thickness]} />
          <meshStandardMaterial {...wallMatProps} />
        </mesh>
      )
      // Window Header (7 to floorHeight)
      const headerHeight = floorHeight - 7.0
      if (headerHeight > 0.05) {
        const cyHeader = baseZ + 7.0 + headerHeight / 2
        panels.push(
          <mesh
            key={`wall-${wall.id}-win-header-${opIdx}`}
            position={[cx - plotWidth / 2, cyHeader, cz - plotDepth / 2]}
            rotation={[0, -angle, 0]}
          >
            <boxGeometry args={[opW, headerHeight, thickness]} />
            <meshStandardMaterial {...wallMatProps} />
          </mesh>
        )
      }
    }

    currentD = opEnd
  })

  // 3. Final solid panel after all openings
  if (currentD + 0.05 < length) {
    const panelL = length - currentD
    const midD = currentD + panelL / 2
    const cx = x1 + midD * ux
    const cy = baseZ + floorHeight / 2
    const cz = y1 + midD * uy

    panels.push(
      <mesh
        key={`wall-${wall.id}-panel-post`}
        position={[cx - plotWidth / 2, cy, cz - plotDepth / 2]}
        rotation={[0, -angle, 0]}
      >
        <boxGeometry args={[panelL, floorHeight, thickness]} />
        <meshStandardMaterial {...wallMatProps} />
      </mesh>
    )
  }

  return <group>{panels}</group>
}

// 3D Procedural Floor Slab with Robust Constructive Geometry
function ProceduralSlab3D({ plotWidth, plotDepth, fLevel, stairCoreRect, baseZ }) {
  const slabThickness = 0.5 // 6-inch architectural RCC structural thickness
  const hw = (plotWidth - 0.1) / 2
  const hd = (plotDepth - 0.1) / 2

  // If upper floor and stairCoreRect exists, subdivide slab around the stairwell cutout
  if (fLevel > 1 && stairCoreRect) {
    const minX = -hw
    const maxX = hw
    const minZ = -hd
    const maxZ = hd

    const rawSx1 = stairCoreRect.x - plotWidth / 2
    const rawSz1 = stairCoreRect.y - plotDepth / 2
    const rawSx2 = rawSx1 + stairCoreRect.w
    const rawSz2 = rawSz1 + stairCoreRect.h

    // Clamp hole coordinates cleanly inside slab bounds
    const hMinX = Math.max(minX, Math.min(maxX, rawSx1))
    const hMaxX = Math.max(minX, Math.min(maxX, rawSx2))
    const hMinZ = Math.max(minZ, Math.min(maxZ, rawSz1))
    const hMaxZ = Math.max(minZ, Math.min(maxZ, rawSz2))

    const subSlabs = []

    // 1. Left slab (from minX to hMinX)
    if (hMinX - minX > 0.05) {
      const w = hMinX - minX
      const cx = minX + w / 2
      subSlabs.push(
        <mesh key="slab-left" position={[cx, baseZ + slabThickness / 2, 0]}>
          <boxGeometry args={[w, slabThickness, plotDepth - 0.1]} />
          <meshStandardMaterial color="#1e293b" roughness={0.8} />
        </mesh>
      )
    }

    // 2. Right slab (from hMaxX to maxX)
    if (maxX - hMaxX > 0.05) {
      const w = maxX - hMaxX
      const cx = hMaxX + w / 2
      subSlabs.push(
        <mesh key="slab-right" position={[cx, baseZ + slabThickness / 2, 0]}>
          <boxGeometry args={[w, slabThickness, plotDepth - 0.1]} />
          <meshStandardMaterial color="#1e293b" roughness={0.8} />
        </mesh>
      )
    }

    // 3. Front slab (between hMinX & hMaxX, from minZ to hMinZ)
    if (hMaxX - hMinX > 0.05 && hMinZ - minZ > 0.05) {
      const w = hMaxX - hMinX
      const d = hMinZ - minZ
      const cx = (hMinX + hMaxX) / 2
      const cz = minZ + d / 2
      subSlabs.push(
        <mesh key="slab-front" position={[cx, baseZ + slabThickness / 2, cz]}>
          <boxGeometry args={[w, slabThickness, d]} />
          <meshStandardMaterial color="#1e293b" roughness={0.8} />
        </mesh>
      )
    }

    // 4. Back slab (between hMinX & hMaxX, from hMaxZ to maxZ)
    if (hMaxX - hMinX > 0.05 && maxZ - hMaxZ > 0.05) {
      const w = hMaxX - hMinX
      const d = maxZ - hMaxZ
      const cx = (hMinX + hMaxX) / 2
      const cz = hMaxZ + d / 2
      subSlabs.push(
        <mesh key="slab-back" position={[cx, baseZ + slabThickness / 2, cz]}>
          <boxGeometry args={[w, slabThickness, d]} />
          <meshStandardMaterial color="#1e293b" roughness={0.8} />
        </mesh>
      )
    }

    return <group>{subSlabs}</group>
  }

  // Full solid slab for ground floor or when no stair core is specified
  return (
    <mesh position={[0, baseZ + slabThickness / 2, 0]}>
      <boxGeometry args={[plotWidth - 0.1, slabThickness, plotDepth - 0.1]} />
      <meshStandardMaterial color="#1e293b" roughness={0.8} />
    </mesh>
  )
}

// 3D Roof Terrace with Parapet Walls and Staircase Headroom Cabin (Mumty)
function ProceduralRoofAndMumty3D({ plotWidth, plotDepth, topZ, stairCoreRect }) {
  const parapetHeight = 3.0 // 3.0 ft height
  const t = 0.5 // 6-inch parapet thickness
  const w = plotWidth - 0.1
  const d = plotDepth - 0.1

  return (
    <group position={[0, topZ, 0]}>
      {/* 1. Roof Terrace Floor Slab */}
      <ProceduralSlab3D
        plotWidth={plotWidth}
        plotDepth={plotDepth}
        fLevel={2}
        stairCoreRect={stairCoreRect}
        baseZ={0}
      />

      {/* 2. Perimeter Parapet Wall (3.0 ft height) */}
      <group position={[0, parapetHeight / 2, 0]}>
        {/* Front Parapet */}
        <mesh position={[0, 0, -d / 2 + t / 2]}>
          <boxGeometry args={[w, parapetHeight, t]} />
          <meshStandardMaterial color="#334155" roughness={0.6} />
        </mesh>
        {/* Back Parapet */}
        <mesh position={[0, 0, d / 2 - t / 2]}>
          <boxGeometry args={[w, parapetHeight, t]} />
          <meshStandardMaterial color="#334155" roughness={0.6} />
        </mesh>
        {/* Left Parapet */}
        <mesh position={[-w / 2 + t / 2, 0, 0]}>
          <boxGeometry args={[t, parapetHeight, Math.max(0.1, d - 2 * t)]} />
          <meshStandardMaterial color="#334155" roughness={0.6} />
        </mesh>
        {/* Right Parapet */}
        <mesh position={[w / 2 - t / 2, 0, 0]}>
          <boxGeometry args={[t, parapetHeight, Math.max(0.1, d - 2 * t)]} />
          <meshStandardMaterial color="#334155" roughness={0.6} />
        </mesh>
      </group>

      {/* 3. Staircase Headroom Cabin (Mumty) */}
      {stairCoreRect && (
        <group
          position={[
            stairCoreRect.x + stairCoreRect.w / 2 - plotWidth / 2,
            0,
            stairCoreRect.y + stairCoreRect.h / 2 - plotDepth / 2,
          ]}
        >
          {/* Mumty Walls (8 ft height) */}
          <mesh position={[0, 4.0, 0]}>
            <boxGeometry args={[stairCoreRect.w, 8.0, stairCoreRect.h]} />
            <meshStandardMaterial color="#cbd5e1" roughness={0.7} />
          </mesh>
          {/* Mumty Concrete Cap Mini-Slab (6-inch thickness) */}
          <mesh position={[0, 8.25, 0]}>
            <boxGeometry args={[stairCoreRect.w + 0.5, 0.5, stairCoreRect.h + 0.5]} />
            <meshStandardMaterial color="#1e293b" roughness={0.8} />
          </mesh>
          {/* Terrace Exit Door */}
          <mesh position={[0, 3.5, stairCoreRect.h / 2 + 0.05]}>
            <boxGeometry args={[3.0, 7.0, 0.1]} />
            <meshStandardMaterial color="#4e3629" roughness={0.6} />
          </mesh>
        </group>
      )}
    </group>
  )
}

function BuildingModel({ buildingData, activeFloorFilter, actualFloors }) {
  if (!buildingData) return null

  const { width: plotWidth, depth: plotDepth, boundaries } = buildingData
  const floorHeight = 10.0
  const totalActualFloors = actualFloors?.length || 1

  // Bounding boxes calculations
  let stairCoreRect = null
  if (boundaries?.stair_core && boundaries.stair_core.length > 0) {
    const xs = boundaries.stair_core.map(c => c[0])
    const ys = boundaries.stair_core.map(c => c[1])
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)

    stairCoreRect = {
      x: minX,
      y: minY,
      w: maxX - minX,
      h: maxY - minY
    }
  }

  return (
    <group>
      {/* 1. Ground Plot Concrete Slab */}
      <mesh position={[0, -0.1, 0]}>
        <boxGeometry args={[plotWidth + 4, 0.2, plotDepth + 4]} />
        <meshStandardMaterial color="#11111b" roughness={0.9} />
      </mesh>

      {/* Plot Boundary Border */}
      <mesh position={[0, -0.05, 0]}>
        <boxGeometry args={[plotWidth + 4.1, 0.12, plotDepth + 4.1]} />
        <meshBasicMaterial color="#313244" wireframe />
      </mesh>

      {/* 2. Floors Iterative Renders (Only valid actual floors) */}
      {actualFloors.filter((fLevel) => activeFloorFilter === 'all' || activeFloorFilter === fLevel).map((fLevel) => {
        const floorData = buildingData.floors_data?.[fLevel] || buildingData.floors_data?.[`${fLevel}`]
        if (!floorData) return null

        const fIdx = fLevel - 1
        const baseZ = fIdx * floorHeight

        const geometry = floorData.geometry || {}
        const walls = geometry.walls || []
        const doors = geometry.doors || []
        const windows = geometry.windows || []
        const layout = floorData.layout || {}

        return (
          <group key={`floor-group-${fLevel}`}>
            {/* Seamless Manifold Floor Slab with Stair Cutout Hole */}
            <ProceduralSlab3D
              plotWidth={plotWidth}
              plotDepth={plotDepth}
              fLevel={fLevel}
              stairCoreRect={stairCoreRect}
              baseZ={baseZ}
            />

            {/* Room Boxes (semi-transparent volumetric zones with clear color identity) */}
            {Object.entries(layout).map(([roomName, room]) => {
              const rx = room.x + room.width / 2 - plotWidth / 2
              const rz = room.y + room.height / 2 - plotDepth / 2
              const ry = baseZ + floorHeight / 2
              const color = roomColors[room.type] || "#ffffff"
              const isOts = room.type === "OTS"

              if (isOts) return null

              return (
                <group key={`volume-${roomName}`}>
                  <mesh position={[rx, ry, rz]}>
                    <boxGeometry args={[room.width - 0.1, floorHeight - 0.1, room.height - 0.1]} />
                    <meshStandardMaterial
                      color={color}
                      transparent
                      opacity={activeFloorFilter === 'all' ? 0.22 : 0.32}
                      roughness={0.8}
                    />
                  </mesh>
                  {/* Floating HTML Label */}
                  <Html position={[rx, baseZ + floorHeight / 2 + 1, rz]} center distanceFactor={16}>
                    <div className="bg-[#0f172a]/95 border border-slate-700/80 px-2 py-1 rounded text-[10px] font-mono pointer-events-none select-none text-center shadow-xl min-w-[70px] backdrop-blur-xs">
                      <span className="font-bold uppercase tracking-wider text-[10px]" style={{ color: color }}>
                        {room.type || roomName}
                      </span>
                      <div className="text-[8px] text-slate-300 font-medium mt-0.5">{room.width}′ × {room.height}′</div>
                    </div>
                  </Html>
                </group>
              )
            })}

            {/* 3D Constructive Walls */}
            {walls.map(w => (
              <ProceduralWall3D
                key={w.id}
                wall={w}
                openings={[...doors, ...windows]}
                floorHeight={floorHeight}
                baseZ={baseZ}
                plotWidth={plotWidth}
                plotDepth={plotDepth}
                isAllFloorsView={activeFloorFilter === 'all'}
              />
            ))}

            {/* 3D Doors */}
            {doors.map(d => {
              const px = d.position[0] - plotWidth / 2
              const pz = d.position[1] - plotDepth / 2
              return (
                <ProceduralDoor3D
                  key={d.id}
                  position={[px, baseZ, pz]}
                  direction={d.direction}
                  width={d.width}
                />
              )
            })}

            {/* 3D Windows */}
            {windows.map(win => {
              const px = win.position[0] - plotWidth / 2
              const pz = win.position[1] - plotDepth / 2
              return (
                <ProceduralWindow3D
                  key={win.id}
                  position={[px, baseZ, pz]}
                  direction={win.direction}
                  width={win.width}
                />
              )
            })}

            {/* 3D Stairs Core Steps (if hosted in core boundaries) */}
            {stairCoreRect && (
              <ProceduralStairs3D
                rect={{
                  x: stairCoreRect.x - plotWidth / 2,
                  y: stairCoreRect.y - plotDepth / 2,
                  w: stairCoreRect.w,
                  h: stairCoreRect.h,
                }}
                floorHeight={floorHeight}
                baseZ={baseZ}
              />
            )}
          </group>
        )
      })}

      {/* 3. Roof Terrace & Stair Headroom Mumty Cabin on top floor */}
      {activeFloorFilter === 'all' && (
        <ProceduralRoofAndMumty3D
          plotWidth={plotWidth}
          plotDepth={plotDepth}
          topZ={totalActualFloors * floorHeight}
          stairCoreRect={stairCoreRect}
        />
      )}

      {/* 4. Structural Columns Pillars */}
      {stairCoreRect && (
        <>
          {[
            [-plotWidth / 2 + 0.2, -plotDepth / 2 + 0.2],
            [plotWidth / 2 - 0.2, -plotDepth / 2 + 0.2],
            [-plotWidth / 2 + 0.2, plotDepth / 2 - 0.2],
            [plotWidth / 2 - 0.2, plotDepth / 2 - 0.2],
          ].map(([colX, colZ], idx) => {
            const pillarHeight = totalActualFloors * floorHeight
            return (
              <mesh key={`pillar-${idx}`} position={[colX, pillarHeight / 2, colZ]}>
                <boxGeometry args={[0.5, pillarHeight, 0.5]} />
                <meshStandardMaterial color="#475569" roughness={0.7} />
              </mesh>
            )
          })}
        </>
      )}
    </group>
  )
}

function CameraBoundsFitter({ plotWidth, plotDepth, buildingHeight, activeFloorFilter, controlsRef }) {
  const { camera } = useThree()

  useEffect(() => {
    if (!plotWidth || !plotDepth) return

    const h = activeFloorFilter === 'all' ? (buildingHeight || 10) : 10
    const centerY = activeFloorFilter === 'all'
      ? (h / 2)
      : (((activeFloorFilter - 1) * 10) + 5)

    const maxDim = Math.max(plotWidth, plotDepth, h)
    const dist = maxDim * 1.25

    // Camera positioned at the FRONT of the house (negative Z, road side) looking towards rear
    camera.position.set(-dist * 0.35, centerY + dist * 0.90, -dist * 1.05)
    camera.lookAt(0, centerY, 0)


    if (controlsRef?.current) {
      controlsRef.current.target.set(0, centerY, 0)
      controlsRef.current.update()
    }
  }, [plotWidth, plotDepth, buildingHeight, activeFloorFilter, camera, controlsRef])

  return null
}

function MockupWireframeMesh() {
  return (
    <group position={[0, 6, 0]}>
      <mesh>
        <boxGeometry args={[10, 14, 10]} />
        <meshBasicMaterial color="#252527" wireframe />
      </mesh>
    </group>
  )
}

/* =========================================================================
   3D CAD Architectural Visualization Primitives (Dimensions, Compass, Axes)
   ========================================================================= */

function CADDimensions3D({ plotWidth, plotDepth, buildingHeight, isVisible }) {
  if (!isVisible || !plotWidth || !plotDepth) return null

  const w = plotWidth
  const d = plotDepth
  const h = buildingHeight || 10
  const dimOffset = 3.0
  const tickSize = 0.9
  const lineThick = 0.08

  return (
    <group position={[0, 0.05, 0]}>
      {/* 1. FRONT WIDTH DIMENSION (X-AXIS) */}
      <group position={[0, 0, -d / 2 - dimOffset]}>
        <mesh position={[0, 0.1, 0]}>
          <boxGeometry args={[w, lineThick, lineThick]} />
          <meshStandardMaterial color="#0284c7" emissive="#0284c7" emissiveIntensity={0.6} />
        </mesh>
        {/* Left extension line */}
        <mesh position={[-w / 2, 0.1, dimOffset / 2]}>
          <boxGeometry args={[lineThick, lineThick, dimOffset + 0.5]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
        {/* Right extension line */}
        <mesh position={[w / 2, 0.1, dimOffset / 2]}>
          <boxGeometry args={[lineThick, lineThick, dimOffset + 0.5]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
        {/* 45-deg CAD Ticks */}
        <mesh position={[-w / 2, 0.1, 0]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[tickSize, lineThick * 1.6, lineThick * 1.6]} />
          <meshStandardMaterial color="#38bdf8" />
        </mesh>
        <mesh position={[w / 2, 0.1, 0]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[tickSize, lineThick * 1.6, lineThick * 1.6]} />
          <meshStandardMaterial color="#38bdf8" />
        </mesh>
        {/* Floating Width Measurement Badge */}
        <Html position={[0, 0.45, 0]} center distanceFactor={22}>
          <div className="bg-[#0b0f19]/95 border border-sky-500/80 px-2 py-0.5 rounded text-[10px] font-mono text-sky-300 font-bold whitespace-nowrap shadow-2xl backdrop-blur-xs flex items-center gap-1.5 select-none pointer-events-none">
            <span className="text-sky-400">↔</span>
            <span>WIDTH: {Math.round(w)}′-0″ ({w.toFixed(1)} ft)</span>
          </div>
        </Html>
      </group>

      {/* 2. SIDE DEPTH DIMENSION (Z-AXIS) */}
      <group position={[-w / 2 - dimOffset, 0, 0]}>
        <mesh position={[0, 0.1, 0]}>
          <boxGeometry args={[lineThick, lineThick, d]} />
          <meshStandardMaterial color="#0284c7" emissive="#0284c7" emissiveIntensity={0.6} />
        </mesh>
        {/* Front extension line */}
        <mesh position={[dimOffset / 2, 0.1, -d / 2]}>
          <boxGeometry args={[dimOffset + 0.5, lineThick, lineThick]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
        {/* Rear extension line */}
        <mesh position={[dimOffset / 2, 0.1, d / 2]}>
          <boxGeometry args={[dimOffset + 0.5, lineThick, lineThick]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
        {/* 45-deg CAD Ticks */}
        <mesh position={[0, 0.1, -d / 2]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[tickSize, lineThick * 1.6, lineThick * 1.6]} />
          <meshStandardMaterial color="#38bdf8" />
        </mesh>
        <mesh position={[0, 0.1, d / 2]} rotation={[0, Math.PI / 4, 0]}>
          <boxGeometry args={[tickSize, lineThick * 1.6, lineThick * 1.6]} />
          <meshStandardMaterial color="#38bdf8" />
        </mesh>
        {/* Floating Depth Measurement Badge */}
        <Html position={[0, 0.45, 0]} center distanceFactor={22}>
          <div className="bg-[#0b0f19]/95 border border-sky-500/80 px-2 py-0.5 rounded text-[10px] font-mono text-sky-300 font-bold whitespace-nowrap shadow-2xl backdrop-blur-xs flex items-center gap-1.5 select-none pointer-events-none">
            <span className="text-sky-400">↕</span>
            <span>DEPTH: {Math.round(d)}′-0″ ({d.toFixed(1)} ft)</span>
          </div>
        </Html>
      </group>

      {/* 3. VERTICAL HEIGHT DIMENSION (Y-AXIS) */}
      <group position={[-w / 2 - 1.8, 0, -d / 2 - 1.8]}>
        <mesh position={[0, h / 2, 0]}>
          <boxGeometry args={[lineThick, h, lineThick]} />
          <meshStandardMaterial color="#059669" emissive="#059669" emissiveIntensity={0.6} />
        </mesh>
        {/* Ground and Top extension flags */}
        <mesh position={[0.7, 0.05, 0.7]}>
          <boxGeometry args={[1.4, lineThick, 1.4]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
        <mesh position={[0.7, h, 0.7]}>
          <boxGeometry args={[1.4, lineThick, 1.4]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
        {/* Ticks */}
        <mesh position={[0, 0.05, 0]}>
          <boxGeometry args={[tickSize, lineThick * 2, tickSize]} />
          <meshStandardMaterial color="#10b981" />
        </mesh>
        <mesh position={[0, h, 0]}>
          <boxGeometry args={[tickSize, lineThick * 2, tickSize]} />
          <meshStandardMaterial color="#10b981" />
        </mesh>
        {/* Floating Height Badge */}
        <Html position={[0, h / 2, 0]} center distanceFactor={22}>
          <div className="bg-[#0b0f19]/95 border border-emerald-500/80 px-2 py-0.5 rounded text-[10px] font-mono text-emerald-300 font-bold whitespace-nowrap shadow-2xl backdrop-blur-xs flex items-center gap-1.5 select-none pointer-events-none">
            <span className="text-emerald-400">▲</span>
            <span>HEIGHT: {Math.round(h)}′-0″ ({h.toFixed(1)} ft)</span>
          </div>
        </Html>
      </group>
    </group>
  )
}

function CADCompassAndDirections3D({ plotWidth, plotDepth, isVisible }) {
  if (!isVisible || !plotWidth || !plotDepth) return null

  const w = plotWidth
  const d = plotDepth
  const cx = w / 2 + 5.5
  const cz = -d / 2 + 5.5

  return (
    <group>
      {/* 1. FRONT ROAD / STREET ACCESS RIBBON */}
      <group position={[0, 0.02, -d / 2 - 5.5]}>
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[w + 14, 0.03, 3.8]} />
          <meshStandardMaterial color="#1e293b" roughness={0.9} />
        </mesh>

        {/* Center dashed line markings */}
        {[-3, -1.5, 0, 1.5, 3].map((off, idx) => (
          <mesh key={`dash-${idx}`} position={[off * (w / 3.2), 0.03, 0]}>
            <boxGeometry args={[2.5, 0.02, 0.2]} />
            <meshBasicMaterial color="#f8fafc" />
          </mesh>
        ))}

        {/* Road Frontage Indicator Badge */}
        <Html position={[0, 0.35, 0]} center distanceFactor={22}>
          <div className="bg-[#0b0f19]/95 border border-sky-400/90 px-3 py-1 rounded text-[10px] font-mono text-sky-300 font-bold tracking-wider shadow-2xl backdrop-blur-xs flex items-center gap-2 whitespace-nowrap select-none pointer-events-none">
            <span className="text-amber-400 font-black">▲</span>
            <span>12.0M FRONT ROAD ACCESS (NBC 2016 COMPLIANT)</span>
            <span className="text-amber-400 font-black">▲</span>
          </div>
        </Html>
      </group>

      {/* 2. GROUND CAD COMPASS ROSE */}
      <group position={[cx, 0.04, cz]}>
        {/* Outer Ring */}
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.2, 2.35, 32]} />
          <meshBasicMaterial color="#38bdf8" />
        </mesh>
        {/* Inner subtle disc */}
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[2.2, 32]} />
          <meshBasicMaterial color="#0f172a" transparent opacity={0.7} />
        </mesh>
        {/* North Pointer Needle (Pointing towards +Z Rear) */}
        <mesh position={[0, 0.02, 1.1]}>
          <coneGeometry args={[0.35, 1.7, 4]} />
          <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.6} />
        </mesh>
        {/* South Needle Pointer */}
        <mesh position={[0, 0.02, -1.1]} rotation={[0, Math.PI, 0]}>
          <coneGeometry args={[0.35, 1.7, 4]} />
          <meshStandardMaterial color="#64748b" />
        </mesh>
        {/* Pivot pin */}
        <mesh position={[0, 0.04, 0]}>
          <cylinderGeometry args={[0.18, 0.18, 0.08, 16]} />
          <meshStandardMaterial color="#f8fafc" />
        </mesh>

        {/* Cardinal North Label */}
        <Html position={[0, 0.25, 2.6]} center distanceFactor={18}>
          <div className="bg-[#0b0f19]/95 border border-red-500/80 px-1.5 py-0.5 rounded text-[10px] font-mono text-red-400 font-black shadow-lg select-none pointer-events-none">
            ⮝ NORTH (+Z)
          </div>
        </Html>
        {/* East / West / South Markers */}
        <Html position={[2.5, 0.25, 0]} center distanceFactor={18}>
          <div className="text-[9px] font-mono text-slate-400 font-bold select-none pointer-events-none">E</div>
        </Html>
        <Html position={[-2.5, 0.25, 0]} center distanceFactor={18}>
          <div className="text-[9px] font-mono text-slate-400 font-bold select-none pointer-events-none">W</div>
        </Html>
        <Html position={[0, 0.25, -2.5]} center distanceFactor={18}>
          <div className="text-[9px] font-mono text-slate-400 font-bold select-none pointer-events-none">S</div>
        </Html>
      </group>
    </group>
  )
}

function CADOriginAxesGizmo3D({ plotWidth, plotDepth, isVisible }) {
  if (!isVisible || !plotWidth || !plotDepth) return null

  const ox = -plotWidth / 2
  const oy = 0.05
  const oz = -plotDepth / 2
  const axisLen = 5.5
  const radius = 0.05

  return (
    <group position={[ox, oy, oz]}>
      {/* Central Origin Node */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.18, 16, 16]} />
        <meshStandardMaterial color="#f8fafc" emissive="#f8fafc" emissiveIntensity={0.6} />
      </mesh>

      {/* X Axis (Red - Width) */}
      <group position={[axisLen / 2, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <mesh>
          <cylinderGeometry args={[radius, radius, axisLen, 8]} />
          <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.5} />
        </mesh>
      </group>
      <mesh position={[axisLen + 0.25, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.2, 0.5, 8]} />
        <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={0.8} />
      </mesh>
      <Html position={[axisLen + 1.1, 0.2, 0]} center distanceFactor={18}>
        <span className="bg-[#450a0a]/90 border border-red-500/80 px-1.5 py-0.5 rounded text-[9px] font-mono text-red-300 font-bold shadow-md select-none pointer-events-none">
          +X (Width)
        </span>
      </Html>

      {/* Y Axis (Green - Elevation / Height) */}
      <group position={[0, axisLen / 2, 0]}>
        <mesh>
          <cylinderGeometry args={[radius, radius, axisLen, 8]} />
          <meshStandardMaterial color="#22c55e" emissive="#22c55e" emissiveIntensity={0.5} />
        </mesh>
      </group>
      <mesh position={[0, axisLen + 0.25, 0]}>
        <coneGeometry args={[0.2, 0.5, 8]} />
        <meshStandardMaterial color="#22c55e" emissive="#22c55e" emissiveIntensity={0.8} />
      </mesh>
      <Html position={[0, axisLen + 1.1, 0]} center distanceFactor={18}>
        <span className="bg-[#052e16]/90 border border-emerald-500/80 px-1.5 py-0.5 rounded text-[9px] font-mono text-emerald-300 font-bold shadow-md select-none pointer-events-none">
          +Y (Height)
        </span>
      </Html>

      {/* Z Axis (Blue - Depth / Rear) */}
      <group position={[0, 0, axisLen / 2]} rotation={[Math.PI / 2, 0, 0]}>
        <mesh>
          <cylinderGeometry args={[radius, radius, axisLen, 8]} />
          <meshStandardMaterial color="#3b82f6" emissive="#3b82f6" emissiveIntensity={0.5} />
        </mesh>
      </group>
      <mesh position={[0, 0, axisLen + 0.25]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.2, 0.5, 8]} />
        <meshStandardMaterial color="#3b82f6" emissive="#3b82f6" emissiveIntensity={0.8} />
      </mesh>
      <Html position={[0, 0.2, axisLen + 1.1]} center distanceFactor={18}>
        <span className="bg-[#172554]/90 border border-blue-500/80 px-1.5 py-0.5 rounded text-[9px] font-mono text-blue-300 font-bold shadow-md select-none pointer-events-none">
          +Z (Depth)
        </span>
      </Html>
    </group>
  )
}

export function BuildingViewer3D({ buildingData, isLoading, isFullscreen, onToggleFullscreen }) {
  const [activeFloorFilter, setActiveFloorFilter] = useState('all')
  const [showDimensions, setShowDimensions] = useState(true)
  const [showCompass, setShowCompass] = useState(true)
  const [showAxes, setShowAxes] = useState(true)
  const controlsRef = useRef(null)

  // Extract only floors that actually exist and contain real spatial data
  const actualFloors = useMemo(() => {
    if (!buildingData?.floors_data) {
      if (buildingData?.floors) {
        return Array.from({ length: buildingData.floors }, (_, i) => i + 1)
      }
      return [1]
    }
    const validFloors = Object.entries(buildingData.floors_data)
      .filter(([_, fData]) => {
        const hasRooms = fData?.layout && Object.keys(fData.layout).length > 0
        const hasWalls = fData?.geometry?.walls && fData.geometry.walls.length > 0
        return hasRooms || hasWalls
      })
      .map(([k]) => parseInt(k))
      .sort((a, b) => a - b)
    return validFloors.length > 0 ? validFloors : [1]
  }, [buildingData])

  // Reset activeFloorFilter if currently selected floor is not in actualFloors
  useEffect(() => {
    if (activeFloorFilter !== 'all' && !actualFloors.includes(activeFloorFilter)) {
      setActiveFloorFilter('all')
    }
  }, [actualFloors, activeFloorFilter])

  // Snap camera to CAD viewport presets (Isometric, Front, Top, Side)
  const setCameraView = (view) => {
    if (!controlsRef?.current) return
    const plotW = buildingData?.width || 40
    const plotD = buildingData?.depth || 40
    const h = (actualFloors?.length || 1) * 10
    const maxDim = Math.max(plotW, plotD, h)
    const dist = maxDim * 1.35
    const centerY = h / 2

    controlsRef.current.target.set(0, centerY, 0)

    if (view === 'iso') {
      controlsRef.current.object.position.set(-dist * 0.45, centerY + dist * 0.85, -dist * 0.95)
    } else if (view === 'front') {
      controlsRef.current.object.position.set(0, centerY + 1, -dist * 1.2)
    } else if (view === 'top') {
      controlsRef.current.object.position.set(0, dist * 1.5, 0.01)
    } else if (view === 'side') {
      controlsRef.current.object.position.set(-dist * 1.25, centerY + 1, 0)
    }
    controlsRef.current.update()
  }

  return (
    <div className="relative w-full h-full bg-[#0a0a0f] flex flex-col">
      {/* Floors selection controls: Data-Driven Floor Tabs */}
      {buildingData && (
        <div className="absolute top-4 left-4 z-10 flex gap-1 bg-[#0d0e15]/90 border border-border p-1 rounded-sm shadow-md font-mono text-[10px]">
          <button
            onClick={() => setActiveFloorFilter('all')}
            className={`px-3 py-1.5 uppercase transition-colors cursor-pointer rounded-xs ${activeFloorFilter === 'all' ? 'bg-primary/20 text-primary font-bold' : 'text-muted-foreground hover:text-foreground'}`}
          >
            Show All Floors
          </button>
          {actualFloors.map((fLevel) => (
            <button
              key={fLevel}
              onClick={() => setActiveFloorFilter(fLevel)}
              className={`px-3 py-1.5 uppercase transition-colors cursor-pointer rounded-xs ${activeFloorFilter === fLevel ? 'bg-primary/20 text-primary font-bold' : 'text-muted-foreground hover:text-foreground'}`}
            >
              Floor {fLevel}
            </button>
          ))}
        </div>
      )}

      {/* Top Controls: Interactive CAD Toolbar & Fullscreen Overlay Button */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        {/* CAD Camera View Presets */}
        {buildingData && (
          <div className="flex items-center gap-1 bg-[#0d0e15]/90 border border-border p-1 rounded-sm shadow-md font-mono text-[10px]">
            <button
              onClick={() => setCameraView('iso')}
              className="px-2 py-1 uppercase text-slate-300 hover:text-primary hover:bg-card transition-colors cursor-pointer rounded-xs"
              title="Axonometric Isometric View"
            >
              Iso
            </button>
            <button
              onClick={() => setCameraView('front')}
              className="px-2 py-1 uppercase text-slate-300 hover:text-primary hover:bg-card transition-colors cursor-pointer rounded-xs"
              title="Front Facade Elevation"
            >
              Front
            </button>
            <button
              onClick={() => setCameraView('top')}
              className="px-2 py-1 uppercase text-slate-300 hover:text-primary hover:bg-card transition-colors cursor-pointer rounded-xs"
              title="Top-Down Plan View"
            >
              Top
            </button>
            <button
              onClick={() => setCameraView('side')}
              className="px-2 py-1 uppercase text-slate-300 hover:text-primary hover:bg-card transition-colors cursor-pointer rounded-xs"
              title="Side Elevation View"
            >
              Side
            </button>
          </div>
        )}

        {/* CAD Element Toggles (Dimensions, Compass, XYZ) */}
        {buildingData && (
          <div className="flex items-center gap-1 bg-[#0d0e15]/90 border border-border p-1 rounded-sm shadow-md font-mono text-[10px]">
            <button
              onClick={() => setShowDimensions(prev => !prev)}
              className={`px-2 py-1 uppercase rounded-xs transition-colors cursor-pointer ${showDimensions ? 'bg-sky-500/20 text-sky-400 font-bold' : 'text-muted-foreground hover:text-foreground'}`}
              title="Toggle 3D CAD Dimensions"
            >
              📐 Dims
            </button>
            <button
              onClick={() => setShowCompass(prev => !prev)}
              className={`px-2 py-1 uppercase rounded-xs transition-colors cursor-pointer ${showCompass ? 'bg-sky-500/20 text-sky-400 font-bold' : 'text-muted-foreground hover:text-foreground'}`}
              title="Toggle Compass & Road Banner"
            >
              🧭 Road
            </button>
            <button
              onClick={() => setShowAxes(prev => !prev)}
              className={`px-2 py-1 uppercase rounded-xs transition-colors cursor-pointer ${showAxes ? 'bg-sky-500/20 text-sky-400 font-bold' : 'text-muted-foreground hover:text-foreground'}`}
              title="Toggle Origin XYZ Axes"
            >
              📍 XYZ
            </button>
          </div>
        )}

        {/* Fullscreen Overlay Button */}
        {onToggleFullscreen && (
          <button
            onClick={onToggleFullscreen}
            className="bg-[#0d0e15]/80 hover:bg-card text-muted-foreground hover:text-foreground border border-border p-2 rounded-sm shadow-md transition-colors cursor-pointer flex items-center justify-center"
            title={isFullscreen ? "Exit Fullscreen (Esc)" : "Fullscreen Mode"}
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        )}
      </div>

      {/* ThreeJS R3F Canvas */}
      <div className="flex-1 w-full h-full relative">
        <CanvasErrorBoundary>
          <Canvas
            camera={{
              position: [40, 35, 40],
              fov: 40,
              near: 0.1,
              far: 1000,
            }}
            dpr={[1, 2]}
          >
            <color attach="background" args={['#07070a']} />

            {/* Lighting systems */}
            <ambientLight intensity={0.6} color="#ffffff" />
            <directionalLight position={[30, 45, 20]} intensity={1.2} color="#ffffff" castShadow />
            <directionalLight position={[-20, 20, -25]} intensity={0.5} color="#818cf8" />
            <pointLight position={[0, 15, 0]} intensity={0.3} color="#38bdf8" />

            {/* Grid base */}
            <Grid
              args={[100, 100]}
              cellSize={1}
              cellColor="#555555"
              sectionSize={5}
              sectionColor="#777777"
              fadeStrength={0.7}
              fadeDistance={75}
              infiniteGrid
            />

            {/* Camera Auto-Fitter */}
            {buildingData && (
              <CameraBoundsFitter
                plotWidth={buildingData.width || 40}
                plotDepth={buildingData.depth || 40}
                buildingHeight={actualFloors.length * 10}
                activeFloorFilter={activeFloorFilter}
                controlsRef={controlsRef}
              />
            )}

            {/* Procedural 3D model generator or Mockup Wireframe Mesh */}
            {buildingData ? (
              <group>
                <BuildingModel
                  buildingData={buildingData}
                  activeFloorFilter={activeFloorFilter}
                  actualFloors={actualFloors}
                />

                {/* 3D CAD Dimensions */}
                <CADDimensions3D
                  plotWidth={buildingData.width}
                  plotDepth={buildingData.depth}
                  buildingHeight={actualFloors.length * 10}
                  isVisible={showDimensions}
                />

                {/* 3D CAD Compass & Front Road Banner */}
                <CADCompassAndDirections3D
                  plotWidth={buildingData.width}
                  plotDepth={buildingData.depth}
                  isVisible={showCompass}
                />

                {/* 3D CAD Origin XYZ Triad */}
                <CADOriginAxesGizmo3D
                  plotWidth={buildingData.width}
                  plotDepth={buildingData.depth}
                  isVisible={showAxes}
                />
              </group>
            ) : (
              <MockupWireframeMesh />
            )}

            {/* Interactive CAD Orientation Viewport Triad Gizmo in bottom-right */}
            <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
              <GizmoViewport
                axisColors={['#ef4444', '#22c55e', '#3b82f6']}
                labelColor="#ffffff"
              />
            </GizmoHelper>

            {/* Orbit navigation controls */}
            <OrbitControls
              ref={controlsRef}
              autoRotate={!buildingData}
              autoRotateSpeed={0.4}
              minDistance={10}
              maxDistance={150}
              enableDamping
              dampingFactor={0.05}
            />
          </Canvas>
        </CanvasErrorBoundary>
      </div>


      {/* Overlay Status */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/75 backdrop-blur-sm z-35">
          <div className="flex flex-col items-center gap-4 bg-card border border-border p-6 rounded-md shadow-2xl">
            <div className="w-10 h-10 border-4 border-accent/20 border-t-accent rounded-full animate-spin" />
            <div className="text-center">
              <h4 className="text-sm font-semibold text-foreground uppercase tracking-wider font-mono">Building Geometry</h4>
              <p className="text-xs text-muted-foreground font-mono mt-1">Executing constructive extrusions and placing models...</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
