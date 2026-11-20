// A 3D VRM avatar for the intro: the same voice-driven mouth, blinking and
// gestures as the 2D rig, on a VRM model drawn with three.js.
//
// Remotion renders each frame on its own, so nothing here keeps state
// between frames: the pose is a pure function of the frame number.
// Spring bones (swaying hair, skirts) need continuous time and are not run.

import { ThreeCanvas } from "@remotion/three";
import { VRM, VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import { useEffect, useMemo, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import type { Mouth } from "./visemes";

/** The VRM 1.0 mouth expression for each Japanese vowel; `n` is closed. */
const MOUTH_EXPRESSION: Record<Mouth, string | null> = {
  a: "aa",
  i: "ih",
  u: "ou",
  e: "ee",
  o: "oh",
  n: null,
};
const MOUTH_EXPRESSIONS = ["aa", "ih", "ou", "ee", "oh"];

type Euler3 = [number, number, number];
type Pose = Partial<Record<string, Euler3>>;

/**
 * Arm poses (radians) for the VRM's normalised humanoid, which stands in a
 * T-pose facing +z: a left arm (the character's left, +x) lowers with a
 * negative z turn, a right arm with a positive one.
 */
const REST_ARMS: Pose = {
  leftUpperArm: [0.12, 0, -1.25],
  rightUpperArm: [0.12, 0, 1.25],
  leftLowerArm: [0, -0.45, -0.12],
  rightLowerArm: [0, 0.45, 0.12],
};
export const POSES: Record<string, Pose> = {
  rest: REST_ARMS,
  // Both hands out in front, palms up: "let's look at this".
  explain: {
    leftUpperArm: [0.15, 0.5, -1.0],
    rightUpperArm: [0.15, -0.5, 1.0],
    leftLowerArm: [0, 1.0, -0.2],
    rightLowerArm: [0, -1.0, 0.2],
  },
  // The right arm (viewer's left of the body, away from the board) rests;
  // the left arm lifts towards the board.
  point: {
    leftUpperArm: [0.1, 0.35, -0.55],
    rightUpperArm: [0, 0, 1.25],
    leftLowerArm: [0, 0.5, -0.1],
    rightLowerArm: [0, 0, 0.12],
  },
  pointer: {
    leftUpperArm: [0.1, 0.3, -0.45],
    rightUpperArm: [0, 0, 1.25],
    leftLowerArm: [0, 0.2, -0.05],
    rightLowerArm: [0, 0, 0.12],
  },
  // A hand up by the chin: "a tip".
  tip: {
    leftUpperArm: [0, 0, -1.25],
    rightUpperArm: [0.3, -0.2, 0.9],
    leftLowerArm: [0, 0, -0.12],
    rightLowerArm: [0, -2.0, 0.3],
  },
};

const ARM_BONES = ["leftUpperArm", "rightUpperArm", "leftLowerArm", "rightLowerArm"];

export type VrmConfig = {
  /** File under public/avatars/<folder>/. */
  file: string;
  /** Camera position and look-at point, in metres (default: upper body). */
  camera?: [number, number, number];
  target?: [number, number, number];
  /** Vertical field of view in degrees (default 28). */
  fov?: number;
  /** Turn the model about Y, in degrees (default 0, facing the camera). */
  yaw?: number;
};

export type VrmPoseState = {
  frame: number;
  fps: number;
  mouth: Mouth;
  /** 0..1 how far into the current vowel, for easing the mouth open and shut. */
  mouthBlend: number;
  blinking: boolean;
  smiling: boolean;
  speaking: boolean;
  gesture: string | undefined;
  previousGesture: string | undefined;
  /** 0..1 progress of the change from `previousGesture` to `gesture`. */
  gestureMix: number;
};

/** Load a VRM; renders wait for it with delayRender. */
export function useVrm(url: string): VRM | null {
  const [vrm, setVrm] = useState<VRM | null>(null);
  const [handle] = useState(() => delayRender(`loading ${url}`));
  useEffect(() => {
    let cancelled = false;
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    loader.load(
      url,
      (gltf) => {
        if (cancelled) return;
        const loaded = gltf.userData.vrm as VRM;
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.combineSkeletons(gltf.scene);
        // VRM 0.x models face -z; VRM 1.0 ones face +z.
        VRMUtils.rotateVRM0(loaded);
        loaded.scene.traverse((o) => {
          o.frustumCulled = false;
        });
        setVrm(loaded);
        continueRender(handle);
      },
      undefined,
      (error) => {
        throw new Error(`cannot load ${url}: ${error}`);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url, handle]);
  return vrm;
}

const e = new THREE.Euler();
const q = new THREE.Quaternion();
const mixed = new THREE.Quaternion();

function setBone(vrm: VRM, name: string, rotation: Euler3, extra?: Euler3) {
  const node = vrm.humanoid.getNormalizedBoneNode(name as never);
  if (!node) return;
  e.set(rotation[0] + (extra?.[0] ?? 0), rotation[1] + (extra?.[1] ?? 0), rotation[2] + (extra?.[2] ?? 0));
  node.quaternion.setFromEuler(e);
}

/** Pose the model for one frame. Pure in `state`. */
export function applyPose(vrm: VRM, s: VrmPoseState) {
  const t = s.frame / s.fps;
  const expressions = vrm.expressionManager;
  if (expressions) {
    for (const name of MOUTH_EXPRESSIONS) expressions.setValue(name, 0);
    const open = MOUTH_EXPRESSION[s.mouth];
    if (open) expressions.setValue(open, 0.85 * s.mouthBlend);
    expressions.setValue("blink", s.blinking && !s.smiling ? 1 : 0);
    expressions.setValue("happy", s.smiling ? 1 : 0);
  }

  // Arms: blend the previous gesture's pose into the current one.
  const to = POSES[s.gesture ?? "rest"] ?? REST_ARMS;
  const from = POSES[s.previousGesture ?? s.gesture ?? "rest"] ?? to;
  for (const bone of ARM_BONES) {
    const a = from[bone] ?? REST_ARMS[bone]!;
    const b = to[bone] ?? REST_ARMS[bone]!;
    e.set(a[0], a[1], a[2]);
    q.setFromEuler(e);
    e.set(b[0], b[1], b[2]);
    mixed.setFromEuler(e);
    q.slerp(mixed, s.gestureMix);
    const node = vrm.humanoid.getNormalizedBoneNode(bone as never);
    if (node) node.quaternion.copy(q);
  }

  // Breathing, a slow sway and a small nod while speaking.
  const breathe = Math.sin(t * 1.9) * 0.012;
  const sway = Math.sin(t * 0.9) * 0.025;
  const nod = s.speaking ? Math.sin(t * 7.5) * 0.03 : 0;
  setBone(vrm, "spine", [breathe, sway * 0.5, 0]);
  setBone(vrm, "chest", [breathe, sway * 0.5, 0]);
  setBone(vrm, "head", [nod, sway, Math.sin(t * 1.1) * 0.03]);
  vrm.update(0);
}

export const VrmAvatar: React.FC<{
  folder: string;
  config: VrmConfig;
  width: number;
  height: number;
  state: VrmPoseState;
}> = ({ folder, config, width, height, state }) => {
  const vrm = useVrm(staticFile(`avatars/${folder}/${config.file}`));
  const camera = useMemo(() => {
    const c = new THREE.PerspectiveCamera(config.fov ?? 28, width / height, 0.1, 20);
    c.position.set(...(config.camera ?? [0, 1.3, 2.6]));
    c.lookAt(...(config.target ?? [0, 1.2, 0]));
    return c;
  }, [config, width, height]);

  useEffect(() => {
    if (vrm) vrm.scene.rotation.y = THREE.MathUtils.degToRad(config.yaw ?? 0);
  }, [vrm, config.yaw]);
  if (vrm) applyPose(vrm, state);

  return (
    <ThreeCanvas width={width} height={height} camera={camera} gl={{ alpha: true, antialias: true }}>
      <ambientLight intensity={1.4} />
      <directionalLight position={[1.2, 2.5, 2.5]} intensity={2.2} />
      <directionalLight position={[-2, 1, 1]} intensity={0.8} color="#ffd6e4" />
      {vrm && <primitive object={vrm.scene} />}
    </ThreeCanvas>
  );
};
