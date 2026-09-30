"use client";

import { Component, useEffect, useMemo, useRef, useState, type ErrorInfo, type MutableRefObject, type ReactNode } from "react";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import Image from "next/image";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone as cloneSkeleton } from "three/addons/utils/SkeletonUtils.js";
import * as THREE from "three";

import { defaultProjectionAnchors, type OperatorAssetStatus, type OperatorRuntime, type ProjectionAnchor, type ProjectionAnchorName } from "@/lib/operator-runtime";

const DEFAULT_ANCHORS = defaultProjectionAnchors();
const PORTRAIT_URL = "/images/aegis-operator-storyboard-sprite.png";

export function CinematicOperatorCanvas({
  runtime,
  onAnchors,
  onAssetStatus,
}: {
  runtime: OperatorRuntime;
  onAnchors: (anchors: Record<ProjectionAnchorName, ProjectionAnchor>) => void;
  onAssetStatus?: (status: OperatorAssetStatus) => void;
}) {
  const [webglSupported] = useState(() => {
    if (typeof window === "undefined" || !("WebGLRenderingContext" in window)) return false;
    try {
      const canvas = document.createElement("canvas");
      return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
    } catch {
      return false;
    }
  });

  useEffect(() => {
    onAnchors(DEFAULT_ANCHORS);
  }, [onAnchors]);

  useEffect(() => onAssetStatus?.("ready"), [onAssetStatus]);

  return (
    <div className="operator-webgl-stage" data-asset-status="ready" data-operator-state={runtime.state} data-operator-target={runtime.target ?? "core"} data-gesture={runtime.activeGesture}>
      {webglSupported ? <Canvas
        dpr={[1, 1.75]}
        camera={{ fov: 28, position: [0, 0.8, 5.8] }}
        gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
        fallback={<div className="operator-webgl-unavailable">WebGL is required for the Aegis operator runtime.</div>}
      >
        <SceneLighting />
        <OperatorFloor />
      </Canvas> : null}
      <AegisOperatorPortrait runtime={runtime} />
    </div>
  );
}

function AegisOperatorPortrait({ runtime }: { runtime: OperatorRuntime }) {
  const target = targetPoint(runtime);
  const actionState = runtime.state === "EXECUTING" || runtime.state === "PRESENTING";
  const pose = actionState && target && target.x < 45 ? "left"
    : actionState && target && target.x > 55 ? "right"
      : runtime.state === "WARNING" || runtime.state === "ERROR" ? "left"
        : "center";
  return <div className="aegis-operator-portrait" data-operator-state={runtime.state} data-operator-pose={pose} data-operator-target={runtime.target ?? "core"} role="img" aria-label={`Aegis AI operator. ${runtime.state.toLowerCase()}.`}>
    <i className="aegis-operator-portrait-aura" aria-hidden />
    <i className="aegis-operator-life-signal" aria-hidden />
    {(["left", "center", "right"] as const).map((name) => <span key={name} className={`aegis-operator-pose aegis-operator-pose-${name}`} aria-hidden>
      <Image src={PORTRAIT_URL} alt="" width={1877} height={838} sizes="(max-width: 800px) 88vw, 45vw" priority />
    </span>)}
  </div>;
}

/* ─── Scene lighting ─────────────────────────────────────────────────── */

function SceneLighting() {
  return <>
    <ambientLight intensity={0.5} color="#c4e8ff" />
    {/* Key light — above-right, warm-white fill */}
    <directionalLight position={[3, 5, 4]} intensity={1.8} color="#f0f8ff" />
    {/* Rim light — behind, cyan accent edge */}
    <pointLight position={[0, 2.5, -2]} intensity={4} color="#5ee8ff" distance={7} />
    {/* Fill lights for arm/hand readability */}
    <pointLight position={[-2.5, 1.5, 2.5]} intensity={2.5} color="#5ec8ff" distance={6} />
    <pointLight position={[2.5, 1.5, 2.5]} intensity={2.5} color="#5ec8ff" distance={6} />
    {/* Under-glow for base */}
    <pointLight position={[0, -1.5, 0.5]} intensity={2} color="#30d4ff" distance={3.5} />
  </>;
}

/* ─── Floor ──────────────────────────────────────────────────────────── */

function OperatorFloor() {
  return <group position={[0, -1.72, 0]}>
    <mesh rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.6, 2.6, 64]} />
      <meshBasicMaterial color="#2ad6ff" transparent opacity={0.06} depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
      <ringGeometry args={[0.9, 1.0, 64]} />
      <meshBasicMaterial color="#5ee8ff" transparent opacity={0.18} depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
  </group>;
}

/* ─── DOM fallback when no WebGL ─────────────────────────────────────── */

function HolographicOperatorDomFallback() {
  return <div className="operator-dom-fallback" role="img" aria-label="Holographic Aegis operator">
    <i className="operator-dom-halo" />
    <i className="operator-dom-head" />
    <i className="operator-dom-visor" />
    <i className="operator-dom-neck" />
    <i className="operator-dom-torso" />
    <i className="operator-dom-arm operator-dom-arm-left" />
    <i className="operator-dom-arm operator-dom-arm-right" />
    <i className="operator-dom-base operator-dom-base-near" />
    <i className="operator-dom-base operator-dom-base-far" />
  </div>;
}

class OperatorModelBoundary extends Component<{ children: ReactNode; runtime: OperatorRuntime; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { this.props.onFailure(); }
  render() { return this.state.failed ? <ProceduralAegisRobot runtime={this.props.runtime} onAnchors={() => {}} /> : this.props.children; }
}

/* ═══════════════════════════════════════════════════════════════════════
   PROCEDURAL AEGIS ROBOT — Full coherent white AI operator
   ═══════════════════════════════════════════════════════════════════════ */

/* ─── Materials ──────────────────────────────────────────────────────── */

/** Primary white armor plate — solid, clean, premium. */
function useArmorMaterial() {
  return useMemo(() => new THREE.MeshStandardMaterial({
    color: "#e4ecf0",
    metalness: 0.35,
    roughness: 0.22,
  }), []);
}

/** Darker panel / tech accent — charcoal with cyan emission. */
function usePanelMaterial() {
  return useMemo(() => new THREE.MeshStandardMaterial({
    color: "#1a2a35",
    emissive: "#18748a",
    emissiveIntensity: 0.35,
    metalness: 0.6,
    roughness: 0.25,
  }), []);
}

/** Joint / flex segment — dark, subtle glow. */
function useFlexMaterial() {
  return useMemo(() => new THREE.MeshStandardMaterial({
    color: "#20343e",
    emissive: "#1a7890",
    emissiveIntensity: 0.2,
    metalness: 0.5,
    roughness: 0.35,
  }), []);
}

/** Visor face — dark translucent panel with strong glow. */
function useVisorMaterial() {
  return useMemo(() => new THREE.MeshPhysicalMaterial({
    color: "#0a1820",
    emissive: "#38d6ff",
    emissiveIntensity: 0.6,
    metalness: 0.9,
    roughness: 0.1,
    transparent: true,
    opacity: 0.88,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
  }), []);
}

/** Bright cyan glow accent lines / energy. */
function useGlowMat(color = "#5de8ff", opacity = 0.92) {
  return useMemo(() => new THREE.MeshBasicMaterial({
    color, transparent: true, opacity, toneMapped: false,
  }), [color, opacity]);
}

/* ─── Smooth-damped lerp ─────────────────────────────────────────────── */

function damp(cur: number, tgt: number, spd: number, dt: number) {
  return THREE.MathUtils.damp(cur, tgt, spd, dt);
}

/* ─── Intent → target poses ──────────────────────────────────────────── */

const TARGET_POSITION: Record<NonNullable<OperatorRuntime["target"]>, { x: number; y: number }> = {
  cameras: { x: 16, y: 24 }, events: { x: 16, y: 43 }, risk: { x: 16, y: 62 },
  evidence: { x: 84, y: 23 }, semantic: { x: 84, y: 40 }, analytics: { x: 84, y: 56 },
  tracking: { x: 80, y: 70 }, incidents: { x: 67, y: 77 }, system: { x: 50, y: 72 },
};

function targetPoint(runtime: OperatorRuntime) {
  return runtime.target ? TARGET_POSITION[runtime.target] : null;
}

function targetBodyYaw(runtime: OperatorRuntime): number {
  const { state } = runtime;
  if (state === "IDLE" || state === "LISTENING" || state === "SPEAKING") return 0;
  const target = targetPoint(runtime);
  return target ? THREE.MathUtils.clamp((50 - target.x) / 34 * 0.36, -0.4, 0.4) : 0;
}
function targetHeadYaw(runtime: OperatorRuntime, t: number): number {
  const { state } = runtime;
  if (state === "IDLE") return Math.sin(t * 0.45) * 0.14;
  if (state === "LISTENING") return 0;
  if (state === "SPEAKING") return Math.sin(t * 0.6) * 0.06;
  const target = targetPoint(runtime);
  return target ? THREE.MathUtils.clamp((50 - target.x) / 34 * 0.48, -0.52, 0.52) : 0;
}

type ArmPose = { rotZ: number; rotX: number };
function leftArmPose(runtime: OperatorRuntime): ArmPose {
  const { state } = runtime;
  const target = targetPoint(runtime);
  if ((state === "EXECUTING" || state === "PRESENTING") && target && target.x < 45)
    return { rotZ: 1.08 + (50 - target.x) * .003, rotX: -.22 - (50 - target.y) * .009 };
  if (state === "SPEAKING") return { rotZ: 0.5, rotX: -0.28 };
  if (state === "LISTENING") return { rotZ: 0.18, rotX: 0.12 };
  if (state === "THINKING") return { rotZ: 0.32, rotX: 0.2 };
  if (state === "WARNING" || state === "ERROR") return { rotZ: 0.85, rotX: -0.32 };
  if (state === "EXECUTING" || state === "PRESENTING") return { rotZ: 0.3, rotX: -0.1 };
  return { rotZ: 0.18, rotX: -0.05 };
}
function rightArmPose(runtime: OperatorRuntime): ArmPose {
  const { state } = runtime;
  const target = targetPoint(runtime);
  if ((state === "EXECUTING" || state === "PRESENTING") && target && target.x > 55)
    return { rotZ: -1.08 - (target.x - 50) * .003, rotX: -.22 - (50 - target.y) * .009 };
  if (state === "SPEAKING") return { rotZ: -0.5, rotX: -0.28 };
  if (state === "LISTENING") return { rotZ: -0.18, rotX: 0.12 };
  if (state === "THINKING") return { rotZ: -0.22, rotX: 0.15 };
  if (state === "WARNING" || state === "ERROR") return { rotZ: -0.85, rotX: -0.32 };
  if (state === "EXECUTING" || state === "PRESENTING") return { rotZ: -0.3, rotX: -0.1 };
  return { rotZ: -0.18, rotX: -0.05 };
}

/* ─── Hand (simplified but readable) ─────────────────────────────────── */

function RobotHand({ armor, flex, fingersRef }: { armor: THREE.Material; flex: THREE.Material; fingersRef: React.RefObject<THREE.Group | null> }) {
  return <group>
    {/* Palm plate */}
    <mesh scale={[0.085, 0.035, 0.1]}>
      <boxGeometry args={[1, 1, 1, 1, 1, 1]} />
      <primitive object={armor} attach="material" />
    </mesh>
    {/* Fingers — 4 main + thumb */}
    <group ref={fingersRef}>
    {[[-0.028, -0.14, 0.08], [-0.009, -0.15, 0.085], [0.012, -0.145, 0.08], [0.031, -0.135, 0.074]].map((pos, i) => (
      <group key={i} position={pos as [number, number, number]} rotation={[0.22, 0, 0]}>
        <mesh><capsuleGeometry args={[0.012, 0.065, 4, 6]} /><primitive object={armor} attach="material" /></mesh>
        <mesh position={[0, -0.05, 0]}><sphereGeometry args={[0.011, 6, 4]} /><primitive object={flex} attach="material" /></mesh>
        <mesh position={[0, -0.08, 0]}><capsuleGeometry args={[0.01, 0.045, 4, 6]} /><primitive object={armor} attach="material" /></mesh>
      </group>
    ))}
    {/* Thumb */}
    <group position={[0.048, -0.01, 0.03]} rotation={[0.3, 0.5, 0.45]}>
      <mesh><capsuleGeometry args={[0.014, 0.05, 4, 6]} /><primitive object={armor} attach="material" /></mesh>
      <mesh position={[0, -0.045, 0]}><capsuleGeometry args={[0.012, 0.035, 4, 6]} /><primitive object={armor} attach="material" /></mesh>
    </group>
    </group>
  </group>;
}

/* ─── The complete robot ─────────────────────────────────────────────── */

function ProceduralAegisRobot({ runtime, onAnchors }: {
  runtime: OperatorRuntime;
  onAnchors: (anchors: Record<ProjectionAnchorName, ProjectionAnchor>) => void;
}) {
  const root = useRef<THREE.Group>(null);
  const headGrp = useRef<THREE.Group>(null);
  const spine = useRef<THREE.Group>(null);
  const lArmGrp = useRef<THREE.Group>(null);
  const rArmGrp = useRef<THREE.Group>(null);
  const lHandGrp = useRef<THREE.Group>(null);
  const rHandGrp = useRef<THREE.Group>(null);
  const lFingerGrp = useRef<THREE.Group>(null);
  const rFingerGrp = useRef<THREE.Group>(null);
  const visorMesh = useRef<THREE.Mesh>(null);
  const shieldMesh = useRef<THREE.Mesh>(null);

  const armor = useArmorMaterial();
  const panel = usePanelMaterial();
  const flex = useFlexMaterial();
  const visorMat = useVisorMaterial();
  const glowCyan = useGlowMat("#5de8ff", 0.9);
  const glowTeal = useGlowMat("#45efc6", 0.85);

  const a = useRef({
    bodyY: 0, headY: 0, headX: 0, headZ: 0,
    lArmZ: 0.18, lArmX: -0.05, rArmZ: -0.18, rArmX: -0.05,
    breath: 0, visorGlow: 0.6,
  });
  const anchorClock = useRef(0);
  const wVec = useMemo(() => new THREE.Vector3(), []);
  const pVec = useMemo(() => new THREE.Vector3(), []);

  useFrame(({ clock, camera }, dt) => {
    const t = clock.getElapsedTime();
    const s = runtime.state;
    const v = a.current;
    const sp = 5; // smoothing speed

    // ── Breath cycle ──
    v.breath += dt * (s === "THINKING" || s === "EXECUTING" ? 1.8 : 1.0);
    const breathY = Math.sin(v.breath * 1.2) * 0.01;
    const breathScale = 1 + Math.sin(v.breath * 1.2) * 0.004;

    // ── Body yaw ──
    v.bodyY = damp(v.bodyY, targetBodyYaw(runtime), sp, dt);
    const idleSway = s === "IDLE" ? Math.sin(t * 0.38) * 0.025 : 0;
    if (root.current) {
      root.current.position.y = -0.25 + breathY;
      root.current.rotation.y = v.bodyY + idleSway;
      root.current.scale.setScalar(breathScale);
    }

    // ── Head ──
    const tHeadY = targetHeadYaw(runtime, t);
    const tHeadX = s === "THINKING" ? 0.14 : s === "LISTENING" ? -0.06 : s === "WARNING" ? -0.08 : Math.sin(t * 0.65) * 0.025;
    const tHeadZ = s === "LISTENING" ? Math.sin(t * 1.6) * 0.035 : 0;
    v.headY = damp(v.headY, tHeadY, sp, dt);
    v.headX = damp(v.headX, tHeadX, sp, dt);
    v.headZ = damp(v.headZ, tHeadZ, sp, dt);
    if (headGrp.current) {
      headGrp.current.rotation.set(v.headX, v.headY, v.headZ);
    }

    // ── Spine lean ──
    if (spine.current) {
      const lean = s === "LISTENING" ? -0.035 : s === "PRESENTING" ? -0.05 : s === "WARNING" ? 0.04 : 0;
      spine.current.rotation.x = damp(spine.current.rotation.x, lean, 3, dt);
    }

    // ── Arms ──
    const lp = leftArmPose(runtime);
    const rp = rightArmPose(runtime);
    const armSway = s === "IDLE" ? Math.sin(t * 0.9) * 0.03 : 0;
    v.lArmZ = damp(v.lArmZ, lp.rotZ + armSway, sp * 0.75, dt);
    v.lArmX = damp(v.lArmX, lp.rotX, sp * 0.75, dt);
    v.rArmZ = damp(v.rArmZ, rp.rotZ - armSway, sp * 0.75, dt);
    v.rArmX = damp(v.rArmX, rp.rotX, sp * 0.75, dt);
    if (lArmGrp.current) { lArmGrp.current.rotation.z = v.lArmZ; lArmGrp.current.rotation.x = v.lArmX; }
    if (rArmGrp.current) { rArmGrp.current.rotation.z = v.rArmZ; rArmGrp.current.rotation.x = v.rArmX; }

    const target = targetPoint(runtime);
    const targeted = s === "EXECUTING" || s === "PRESENTING";
    const handPulse = Math.sin(t * (s === "SPEAKING" ? 2.2 : 1.05));
    if (lHandGrp.current) {
      lHandGrp.current.rotation.y = damp(lHandGrp.current.rotation.y, targeted && target && target.x < 45 ? -.32 : handPulse * .035, 5, dt);
      lHandGrp.current.rotation.z = damp(lHandGrp.current.rotation.z, handPulse * .025, 5, dt);
    }
    if (rHandGrp.current) {
      rHandGrp.current.rotation.y = damp(rHandGrp.current.rotation.y, targeted && target && target.x > 55 ? .32 : -handPulse * .035, 5, dt);
      rHandGrp.current.rotation.z = damp(rHandGrp.current.rotation.z, -handPulse * .025, 5, dt);
    }
    const fingerCurl = targeted ? -.16 : s === "THINKING" ? .1 : Math.sin(t * .8) * .035;
    if (lFingerGrp.current) lFingerGrp.current.rotation.x = damp(lFingerGrp.current.rotation.x, fingerCurl, 4, dt);
    if (rFingerGrp.current) rFingerGrp.current.rotation.x = damp(rFingerGrp.current.rotation.x, fingerCurl, 4, dt);

    // ── Visor glow ──
    const vTarget = s === "LISTENING" ? 0.85 + Math.sin(t * 3.5) * 0.15
      : s === "SPEAKING" ? 0.9 + Math.sin(t * 5) * 0.1
      : s === "THINKING" ? 0.5 + Math.sin(t * 2.2) * 0.25
      : s === "EXECUTING" ? 0.95
      : s === "WARNING" || s === "ERROR" ? 0.5 + Math.sin(t * 2.8) * 0.35
      : 0.55 + Math.sin(t * 1.1) * 0.12;
    v.visorGlow = damp(v.visorGlow, vTarget, 8, dt);
    if (visorMesh.current) {
      const mat = visorMesh.current.material as THREE.MeshPhysicalMaterial;
      mat.emissiveIntensity = v.visorGlow;
      if (s === "WARNING" || s === "ERROR") { mat.emissive.set("#ffaa33"); } else { mat.emissive.set("#38d6ff"); }
    }

    // ── Shield emblem pulse ──
    if (shieldMesh.current) {
      const smat = shieldMesh.current.material as THREE.MeshBasicMaterial;
      smat.opacity = 0.7 + Math.sin(t * 1.8) * 0.25;
      if (s === "WARNING") smat.color.set("#ffb347"); else if (s === "ERROR") smat.color.set("#ff6b7a"); else smat.color.set("#45efc6");
    }

    // ── Projection anchors ──
    if (t - anchorClock.current > 0.1) {
      anchorClock.current = t;
      const result: Record<ProjectionAnchorName, ProjectionAnchor> = { ...DEFAULT_ANCHORS };
      const project = (ref: React.RefObject<THREE.Group | null>, name: ProjectionAnchorName) => {
        if (!ref.current) return;
        ref.current.getWorldPosition(wVec);
        pVec.copy(wVec).project(camera);
        result[name] = {
          x: THREE.MathUtils.clamp((pVec.x + 1) * 50, 8, 92),
          y: THREE.MathUtils.clamp((1 - pVec.y) * 50, 12, 84),
          fromRig: true,
        };
      };
      project(lHandGrp, "leftHandProjectionAnchor");
      project(rHandGrp, "rightHandProjectionAnchor");
      project(lArmGrp, "leftSideProjectionAnchor");
      project(rArmGrp, "rightSideProjectionAnchor");
      project(spine, "centerProjectionAnchor");
      onAnchors(result);
    }
  });

  return (
    <group ref={root} position={[0, -0.25, 0]}>

      {/* ═══ SPINE — everything upper-body leans with this ═══ */}
      <group ref={spine}>

        {/* ════════════════════ HEAD ════════════════════ */}
        <group ref={headGrp} position={[0, 1.54, 0]}>
          {/* Helmet shell — smooth rounded form */}
          <mesh position={[0, 0.04, -0.02]} scale={[1, 1.05, 0.95]}>
            <sphereGeometry args={[0.24, 24, 18]} />
            <primitive object={armor} attach="material" />
          </mesh>
          {/* Helmet top crest / ridge */}
          <mesh position={[0, 0.19, -0.04]} scale={[0.06, 0.04, 0.22]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={panel} attach="material" />
          </mesh>

          {/* ── FACE / VISOR — the identity of the robot ── */}
          <group position={[0, -0.01, 0.19]}>
            {/* Visor frame — wraps around the front of the helmet */}
            <mesh scale={[0.42, 0.17, 0.08]} position={[0, 0.02, 0]}>
              <boxGeometry args={[1, 1, 1, 2, 2, 1]} />
              <primitive object={panel} attach="material" />
            </mesh>
            {/* Visor glass — the dark reflective face panel */}
            <mesh ref={visorMesh} scale={[0.38, 0.11, 0.02]} position={[0, 0.02, 0.035]}>
              <boxGeometry args={[1, 1, 1]} />
              <primitive object={visorMat} attach="material" />
            </mesh>
            {/* Visor glow line — bright horizontal accent across the eyes */}
            <mesh position={[0, 0.02, 0.048]} scale={[0.32, 0.018, 0.005]}>
              <boxGeometry args={[1, 1, 1]} />
              <primitive object={glowCyan} attach="material" />
            </mesh>
            {/* Side visor accent — left */}
            <mesh position={[-0.19, 0.02, -0.01]} scale={[0.025, 0.07, 0.04]}>
              <boxGeometry args={[1, 1, 1]} />
              <primitive object={glowCyan} attach="material" />
            </mesh>
            {/* Side visor accent — right */}
            <mesh position={[0.19, 0.02, -0.01]} scale={[0.025, 0.07, 0.04]}>
              <boxGeometry args={[1, 1, 1]} />
              <primitive object={glowCyan} attach="material" />
            </mesh>
            {/* Visor forward glow */}
            <pointLight position={[0, 0.02, 0.12]} intensity={2.5} color="#42d8ff" distance={1.2} />
          </group>

          {/* Chin / lower face plate — closes the helmet naturally */}
          <mesh position={[0, -0.14, 0.1]} scale={[0.28, 0.06, 0.14]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={armor} attach="material" />
          </mesh>
          {/* Chin vent detail */}
          <mesh position={[0, -0.16, 0.14]} scale={[0.14, 0.015, 0.01]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={flex} attach="material" />
          </mesh>

          {/* Side head panels — audio sensors */}
          <mesh position={[-0.23, 0, 0]} scale={[0.04, 0.1, 0.14]} rotation={[0, 0, 0.15]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={armor} attach="material" />
          </mesh>
          <mesh position={[0.23, 0, 0]} scale={[0.04, 0.1, 0.14]} rotation={[0, 0, -0.15]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={armor} attach="material" />
          </mesh>

          {/* Top antenna / status indicator */}
          <mesh position={[0, 0.3, -0.02]}>
            <cylinderGeometry args={[0.008, 0.015, 0.08, 6]} />
            <primitive object={panel} attach="material" />
          </mesh>
          <mesh position={[0, 0.35, -0.02]}>
            <sphereGeometry args={[0.018, 8, 6]} />
            <primitive object={glowCyan} attach="material" />
          </mesh>
        </group>

        {/* ════════════════════ NECK ════════════════════ */}
        {/* Multi-segment neck so it looks mechanical but connected */}
        <mesh position={[0, 1.33, 0.01]}>
          <cylinderGeometry args={[0.09, 0.11, 0.1, 12]} />
          <primitive object={flex} attach="material" />
        </mesh>
        <mesh position={[0, 1.26, 0.01]}>
          <cylinderGeometry args={[0.11, 0.12, 0.05, 12]} />
          <primitive object={armor} attach="material" />
        </mesh>

        {/* ════════════════════ TORSO ════════════════════ */}
        <group position={[0, 0.72, 0]}>
          {/* Upper chest — wide, heroic proportions */}
          <mesh position={[0, 0.28, 0]} scale={[1.15, 0.9, 0.72]}>
            <capsuleGeometry args={[0.26, 0.18, 10, 18]} />
            <primitive object={armor} attach="material" />
          </mesh>

          {/* Chest center plate detail */}
          <mesh position={[0, 0.3, 0.2]} scale={[0.18, 0.28, 0.03]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={panel} attach="material" />
          </mesh>
          {/* Center line */}
          <mesh position={[0, 0.15, 0.22]} scale={[0.01, 0.5, 0.01]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={flex} attach="material" />
          </mesh>

          {/* Shield / emblem — the AegisAI identity mark */}
          <mesh ref={shieldMesh} position={[0, 0.32, 0.225]}>
            <circleGeometry args={[0.048, 6]} />
            <primitive object={glowTeal} attach="material" />
          </mesh>
          <pointLight position={[0, 0.32, 0.32]} intensity={1.2} color="#45efc6" distance={0.7} />

          {/* Collar / upper chest rim */}
          <mesh position={[0, 0.46, 0.06]} scale={[0.52, 0.035, 0.32]} rotation={[0.15, 0, 0]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={armor} attach="material" />
          </mesh>

          {/* Mid torso — slightly narrower, armored panels */}
          <mesh position={[0, -0.02, 0]} scale={[0.95, 0.75, 0.65]}>
            <capsuleGeometry args={[0.2, 0.18, 8, 16]} />
            <primitive object={armor} attach="material" />
          </mesh>

          {/* Side torso accent lines */}
          <mesh position={[-0.27, 0.15, 0.1]} scale={[0.012, 0.25, 0.01]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={glowCyan} attach="material" />
          </mesh>
          <mesh position={[0.27, 0.15, 0.1]} scale={[0.012, 0.25, 0.01]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={glowCyan} attach="material" />
          </mesh>

          {/* ── Shoulder armor ── */}
          {/* Left shoulder pad */}
          <group position={[-0.38, 0.36, 0]}>
            <mesh scale={[0.16, 0.1, 0.16]}>
              <sphereGeometry args={[0.65, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
              <primitive object={armor} attach="material" />
            </mesh>
            <mesh position={[0, -0.01, 0.08]} scale={[0.06, 0.015, 0.01]}>
              <boxGeometry args={[1, 1, 1]} />
              <primitive object={glowCyan} attach="material" />
            </mesh>
          </group>
          {/* Right shoulder pad */}
          <group position={[0.38, 0.36, 0]}>
            <mesh scale={[0.16, 0.1, 0.16]}>
              <sphereGeometry args={[0.65, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
              <primitive object={armor} attach="material" />
            </mesh>
            <mesh position={[0, -0.01, 0.08]} scale={[0.06, 0.015, 0.01]}>
              <boxGeometry args={[1, 1, 1]} />
              <primitive object={glowCyan} attach="material" />
            </mesh>
          </group>
        </group>

        {/* ════════════════════ LEFT ARM ════════════════════ */}
        <group ref={lArmGrp} position={[-0.52, 0.98, 0]}>
          {/* Shoulder ball joint */}
          <mesh>
            <sphereGeometry args={[0.065, 12, 8]} />
            <primitive object={flex} attach="material" />
          </mesh>
          {/* Upper arm armor */}
          <mesh position={[0, -0.17, 0]} scale={[1, 1, 0.9]}>
            <capsuleGeometry args={[0.058, 0.18, 6, 10]} />
            <primitive object={armor} attach="material" />
          </mesh>
          {/* Bicep glow line */}
          <mesh position={[-0.055, -0.14, 0.03]} scale={[0.008, 0.1, 0.008]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={glowCyan} attach="material" />
          </mesh>
          {/* Elbow joint — overlapping disc */}
          <mesh position={[0, -0.32, 0]}>
            <cylinderGeometry args={[0.052, 0.048, 0.05, 10]} />
            <primitive object={flex} attach="material" />
          </mesh>
          {/* Forearm armor */}
          <mesh position={[0, -0.48, 0]} scale={[0.95, 1, 0.85]}>
            <capsuleGeometry args={[0.05, 0.2, 6, 10]} />
            <primitive object={armor} attach="material" />
          </mesh>
          {/* Forearm accent */}
          <mesh position={[0, -0.46, 0.048]} scale={[0.015, 0.11, 0.008]}>
            <boxGeometry args={[1, 1, 1]} />
            <primitive object={glowCyan} attach="material" />
          </mesh>
          {/* Wrist joint */}
          <mesh position={[0, -0.62, 0]}>
            <cylinderGeometry args={[0.038, 0.042, 0.04, 8]} />
            <primitive object={flex} attach="material" />
          </mesh>
          {/* Hand */}
          <group ref={lHandGrp} position={[0, -0.7, 0.02]}>
            <RobotHand armor={armor} flex={flex} fingersRef={lFingerGrp} />
          </group>
        </group>

        {/* ════════════════════ RIGHT ARM ════════════════════ */}
        <group ref={rArmGrp} position={[0.52, 0.98, 0]}>
          <mesh><sphereGeometry args={[0.065, 12, 8]} /><primitive object={flex} attach="material" /></mesh>
          <mesh position={[0, -0.17, 0]} scale={[1, 1, 0.9]}>
            <capsuleGeometry args={[0.058, 0.18, 6, 10]} /><primitive object={armor} attach="material" />
          </mesh>
          <mesh position={[0.055, -0.14, 0.03]} scale={[0.008, 0.1, 0.008]}>
            <boxGeometry args={[1, 1, 1]} /><primitive object={glowCyan} attach="material" />
          </mesh>
          <mesh position={[0, -0.32, 0]}>
            <cylinderGeometry args={[0.052, 0.048, 0.05, 10]} /><primitive object={flex} attach="material" />
          </mesh>
          <mesh position={[0, -0.48, 0]} scale={[0.95, 1, 0.85]}>
            <capsuleGeometry args={[0.05, 0.2, 6, 10]} /><primitive object={armor} attach="material" />
          </mesh>
          <mesh position={[0, -0.46, 0.048]} scale={[0.015, 0.11, 0.008]}>
            <boxGeometry args={[1, 1, 1]} /><primitive object={glowCyan} attach="material" />
          </mesh>
          <mesh position={[0, -0.62, 0]}>
            <cylinderGeometry args={[0.038, 0.042, 0.04, 8]} /><primitive object={flex} attach="material" />
          </mesh>
          <group ref={rHandGrp} position={[0, -0.7, 0.02]}>
            <RobotHand armor={armor} flex={flex} fingersRef={rFingerGrp} />
          </group>
        </group>

      </group>{/* end spine */}

      {/* ════════════════════ WAIST ════════════════════ */}
      <mesh position={[0, 0.42, 0]}>
        <cylinderGeometry args={[0.18, 0.2, 0.1, 14]} />
        <primitive object={flex} attach="material" />
      </mesh>
      {/* Waist armor ring */}
      <mesh position={[0, 0.38, 0]}>
        <cylinderGeometry args={[0.21, 0.22, 0.04, 14]} />
        <primitive object={armor} attach="material" />
      </mesh>

      {/* ════════════════════ HIP / LOWER BODY ════════════════════ */}
      {/* Smooth tapered lower section — intentional floating design */}
      <mesh position={[0, 0.2, 0]} scale={[1, 1, 0.7]}>
        <cylinderGeometry args={[0.2, 0.28, 0.28, 12]} />
        <primitive object={armor} attach="material" />
      </mesh>

      {/* Upper leg armor plates (thigh guards) — left */}
      <mesh position={[-0.12, -0.02, 0]} scale={[0.09, 0.18, 0.08]}>
        <capsuleGeometry args={[0.5, 0.3, 6, 10]} />
        <primitive object={armor} attach="material" />
      </mesh>
      {/* Upper leg armor — right */}
      <mesh position={[0.12, -0.02, 0]} scale={[0.09, 0.18, 0.08]}>
        <capsuleGeometry args={[0.5, 0.3, 6, 10]} />
        <primitive object={armor} attach="material" />
      </mesh>

      {/* Lower leg / boot forms — left */}
      <mesh position={[-0.12, -0.28, 0]} scale={[0.075, 0.22, 0.07]}>
        <capsuleGeometry args={[0.5, 0.35, 6, 8]} />
        <primitive object={armor} attach="material" />
      </mesh>
      {/* Knee joint — left */}
      <mesh position={[-0.12, -0.14, 0]}>
        <sphereGeometry args={[0.042, 8, 6]} />
        <primitive object={flex} attach="material" />
      </mesh>
      {/* Lower leg / boot — right */}
      <mesh position={[0.12, -0.28, 0]} scale={[0.075, 0.22, 0.07]}>
        <capsuleGeometry args={[0.5, 0.35, 6, 8]} />
        <primitive object={armor} attach="material" />
      </mesh>
      <mesh position={[0.12, -0.14, 0]}>
        <sphereGeometry args={[0.042, 8, 6]} />
        <primitive object={flex} attach="material" />
      </mesh>

      {/* Leg glow accents */}
      <mesh position={[-0.12, -0.22, 0.055]} scale={[0.008, 0.14, 0.006]}>
        <boxGeometry args={[1, 1, 1]} />
        <primitive object={glowCyan} attach="material" />
      </mesh>
      <mesh position={[0.12, -0.22, 0.055]} scale={[0.008, 0.14, 0.006]}>
        <boxGeometry args={[1, 1, 1]} />
        <primitive object={glowCyan} attach="material" />
      </mesh>

      {/* ════════════════════ FEET / BASE ════════════════════ */}
      {/* Left foot */}
      <mesh position={[-0.12, -0.52, 0.02]} scale={[0.06, 0.04, 0.1]}>
        <boxGeometry args={[1, 1, 1]} />
        <primitive object={armor} attach="material" />
      </mesh>
      {/* Right foot */}
      <mesh position={[0.12, -0.52, 0.02]} scale={[0.06, 0.04, 0.1]}>
        <boxGeometry args={[1, 1, 1]} />
        <primitive object={armor} attach="material" />
      </mesh>

      {/* ════════════════════ PLATFORM ════════════════════ */}
      <group position={[0, -0.58, 0]}>
        {/* Inner energy ring */}
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.35, 0.012, 8, 48]} />
          <primitive object={glowCyan} attach="material" />
        </mesh>
        {/* Outer energy ring */}
        <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
          <torusGeometry args={[0.55, 0.006, 8, 64]} />
          <meshBasicMaterial color="#2ad6ff" transparent opacity={0.35} />
        </mesh>
        {/* Platform disc */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
          <circleGeometry args={[0.5, 48]} />
          <meshBasicMaterial color="#2ad6ff" transparent opacity={0.1} depthWrite={false} />
        </mesh>
      </group>

    </group>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   GLB RIGGED OPERATOR — used when aegis-operator.glb is present
   ═══════════════════════════════════════════════════════════════════════ */

const clipTerms: Record<string, string[]> = {
  idle: ["idle", "breath", "neutral"],
  listen: ["listen", "listening", "attention"],
  think: ["think", "thinking", "focus"],
  "speak-neutral": ["speak", "talk", "speaking"],
  "present-left": ["present_left", "present left", "gesture_left", "gesture left"],
  "present-right": ["present_right", "present right", "gesture_right", "gesture right"],
  "point-left": ["point_left", "point left"],
  "point-right": ["point_right", "point right"],
  "summon-left": ["summon_left", "summon left", "reach_left", "reach left"],
  "summon-right": ["summon_right", "summon right", "reach_right", "reach right"],
  "push-forward": ["push", "forward", "present"],
  "warning-attention": ["warning", "alert", "attention"],
};

function normalized(value: string) {
  return value.toLowerCase().replace(/[._-]+/g, " ").trim();
}

function matchingClip(clips: THREE.AnimationClip[], gesture: OperatorRuntime["activeGesture"]) {
  const terms = clipTerms[gesture] ?? [];
  return clips.find((clip) => terms.some((term) => normalized(clip.name).includes(normalized(term))))
    ?? (gesture === "idle" ? undefined : clips.find((clip) => clipTerms.idle.some((term) => normalized(clip.name).includes(term))));
}

type MorphTarget = { mesh: THREE.Mesh; index: number };
type HolographicMaterial = THREE.Material & { userData: { aegisHologramShader?: { uniforms: Record<string, { value: number }> } } };

function holographicMaterial(source: THREE.Material): HolographicMaterial {
  const material = source.clone() as HolographicMaterial & THREE.MeshStandardMaterial;
  material.transparent = true;
  material.opacity = 0.79;
  if ("color" in material) material.color.set("#bcfaff");
  if ("emissive" in material) {
    material.emissive.set("#1689a8");
    material.emissiveIntensity = 0.75;
  }
  if ("metalness" in material) material.metalness = 0.42;
  if ("roughness" in material) material.roughness = 0.34;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.aegisTime = { value: 0 };
    shader.vertexShader = `varying vec3 aegisViewNormal;\n${shader.vertexShader}`.replace(
      "#include <beginnormal_vertex>",
      "#include <beginnormal_vertex>\n aegisViewNormal = normalize(normalMatrix * objectNormal);",
    );
    shader.fragmentShader = `uniform float aegisTime;\nvarying vec3 aegisViewNormal;\n${shader.fragmentShader}`.replace(
      "#include <output_fragment>",
      `float aegisRim = pow(1.0 - abs(aegisViewNormal.z), 2.4);
       float aegisScan = 0.84 + 0.16 * sin(vViewPosition.y * 42.0 + aegisTime * 2.0);
       outgoingLight += vec3(0.08, 0.65, 0.9) * aegisRim * aegisScan;
       #include <output_fragment>`,
    );
    material.userData.aegisHologramShader = shader;
  };
  material.needsUpdate = true;
  return material;
}

function findNode(root: THREE.Object3D, names: string[]) {
  const expected = names.map(normalized);
  let match: THREE.Object3D | null = null;
  root.traverse((node) => {
    if (match) return;
    const name = normalized(node.name);
    if (expected.some((candidate) => name === candidate || name.includes(candidate))) match = node;
  });
  return match;
}

function RiggedAegisOperator({ modelUrl, runtime, onAnchors }: { modelUrl: string; runtime: OperatorRuntime; onAnchors: (anchors: Record<ProjectionAnchorName, ProjectionAnchor>) => void }) {
  const gltf = useLoader(GLTFLoader, modelUrl);
  const group = useRef<THREE.Group>(null);
  const lastAnchorFrameRef = useRef(0);
  const activeAction = useRef<THREE.AnimationAction | null>(null);
  const holographicMaterials = useRef<HolographicMaterial[]>([]);
  const scene = useMemo(() => cloneSkeleton(gltf.scene), [gltf.scene]);
  const mixer = useMemo(() => new THREE.AnimationMixer(scene), [scene]);
  const morphTargets = useMemo(() => {
    const targets: MorphTarget[] = [];
    scene.traverse((node) => {
      if (!(node instanceof THREE.Mesh) || !node.morphTargetDictionary || !node.morphTargetInfluences) return;
      Object.entries(node.morphTargetDictionary).forEach(([name, index]) => {
        if (/(jaw|mouth.*open|viseme.*(aa|ah|oh)|open.*mouth)/i.test(name)) targets.push({ mesh: node, index });
      });
    });
    return targets;
  }, [scene]);
  const anchorNodes = useMemo(() => ({
    rightHandProjectionAnchor: findNode(scene, ["right hand", "hand r", "mixamorig right hand", "wrist r"]),
    leftHandProjectionAnchor: findNode(scene, ["left hand", "hand l", "mixamorig left hand", "wrist l"]),
    rightSideProjectionAnchor: findNode(scene, ["right shoulder", "shoulder r", "mixamorig right arm"]),
    leftSideProjectionAnchor: findNode(scene, ["left shoulder", "shoulder l", "mixamorig left arm"]),
    centerProjectionAnchor: findNode(scene, ["chest", "spine2", "spine 2", "mixamorig spine"]),
  }), [scene]);

  useEffect(() => {
    const generated: HolographicMaterial[] = [];
    scene.traverse((node) => {
      if (!(node instanceof THREE.Mesh)) return;
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      const nextMaterials = materials.map((material) => {
        const next = holographicMaterial(material);
        generated.push(next);
        return next;
      });
      node.material = nextMaterials;
      node.castShadow = false;
      node.receiveShadow = false;
    });
    holographicMaterials.current = generated;
    return () => {
      generated.forEach((material) => material.dispose());
      holographicMaterials.current = [];
    };
  }, [scene]);

  useEffect(() => {
    const clip = matchingClip(gltf.animations, runtime.activeGesture);
    if (!clip) return;
    const next = mixer.clipAction(clip);
    const previous = activeAction.current;
    if (previous === next) return;
    previous?.fadeOut(0.28);
    next.reset().setEffectiveTimeScale(1).setEffectiveWeight(1).fadeIn(0.28).play();
    activeAction.current = next;
  }, [gltf.animations, mixer, runtime.activeGesture]);

  useEffect(() => () => { mixer.stopAllAction(); }, [mixer]);

  return <group ref={group} position={[0, -1.58, 0]}>
    <primitive object={scene} />
    <RigController runtime={runtime} mixer={mixer} holographicMaterials={holographicMaterials} morphTargets={morphTargets} anchorNodes={anchorNodes} lastAnchorFrameRef={lastAnchorFrameRef} onAnchors={onAnchors} />
  </group>;
}

function RigController({
  runtime, mixer, holographicMaterials, morphTargets, anchorNodes, lastAnchorFrameRef, onAnchors,
}: {
  runtime: OperatorRuntime;
  mixer: THREE.AnimationMixer;
  holographicMaterials: MutableRefObject<HolographicMaterial[]>;
  morphTargets: MorphTarget[];
  anchorNodes: Record<ProjectionAnchorName, THREE.Object3D | null>;
  lastAnchorFrameRef: React.MutableRefObject<number>;
  onAnchors: (anchors: Record<ProjectionAnchorName, ProjectionAnchor>) => void;
}) {
  const { camera } = useThree();
  const projected = useMemo(() => new THREE.Vector3(), []);
  const world = useMemo(() => new THREE.Vector3(), []);
  const mouthLevel = useRef(0);

  useFrame((frame, delta) => {
    mixer.update(delta);
    holographicMaterials.current.forEach((material) => {
      const shader = material.userData.aegisHologramShader;
      if (shader) shader.uniforms.aegisTime.value = frame.clock.getElapsedTime();
    });
    const target = runtime.state === "SPEAKING" ? Math.min(1, runtime.speakingLevel * 1.65) : 0;
    mouthLevel.current = THREE.MathUtils.damp(mouthLevel.current, target, 18, delta);
    morphTargets.forEach(({ mesh, index }) => {
      if (mesh.morphTargetInfluences) mesh.morphTargetInfluences[index] = mouthLevel.current;
    });
    if (frame.clock.elapsedTime - lastAnchorFrameRef.current < 0.1) return;
    lastAnchorFrameRef.current = frame.clock.elapsedTime;
    const anchors = Object.fromEntries((Object.keys(DEFAULT_ANCHORS) as ProjectionAnchorName[]).map((name) => {
      const node = anchorNodes[name];
      if (!node) return [name, DEFAULT_ANCHORS[name]];
      node.getWorldPosition(world);
      projected.copy(world).project(camera);
      return [name, {
        x: THREE.MathUtils.clamp((projected.x + 1) * 50, 8, 92),
        y: THREE.MathUtils.clamp((1 - projected.y) * 50, 12, 84),
        fromRig: true,
      }];
    })) as Record<ProjectionAnchorName, ProjectionAnchor>;
    onAnchors(anchors);
  });
  return null;
}
