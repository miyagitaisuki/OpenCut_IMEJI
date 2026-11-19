import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import type { IntroProps } from "./types";
import { mouthAt } from "./visemes";

/** Seconds before the avatar starts talking, and after it stops. */
export const LEAD_IN = 0.8;
export const TAIL = 1.2;

export const Intro: React.FC<IntroProps> = ({ scene, avatar, voice, voiceSeconds, visemes }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const seconds = frame / fps;
  const [from, to] = scene.colors ?? ["#ffd6e4", "#2b3a67"];

  const enter = spring({ frame, fps, config: { damping: 14 } });
  const card = spring({ frame: frame - fps * 0.3, fps, config: { damping: 16 } });
  const talking = seconds - LEAD_IN;

  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${from} 0%, ${to} 100%)`, overflow: "hidden" }}>
      <Petals frame={frame} width={width} height={height} />
      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: -60,
          transform: `translateY(${(1 - enter) * 400}px)`,
        }}
      >
        <Avatar
          avatar={avatar}
          frame={frame}
          fps={fps}
          mouth={mouthAt(visemes, talking)}
          gesture={gestureTimeline(scene.gestures, talking, LEAD_IN, fps)}
          smiling={talking > voiceSeconds + 0.3}
        />
        {scene.effects && <Effects avatar={avatar} effects={scene.effects} frame={frame} fps={fps} />}
      </div>
      <div
        style={{
          position: "absolute",
          right: 140,
          top: 230,
          width: 860,
          opacity: card,
          transform: `translateX(${(1 - card) * 120}px)`,
          fontFamily: '"Noto Sans CJK JP", "Noto Sans JP", sans-serif',
          color: "#fff",
          textShadow: "0 6px 24px rgba(0,0,0,.35)",
        }}
      >
        {scene.subtitle && (
          <div
            style={{
              display: "inline-block",
              fontSize: 56,
              fontWeight: 700,
              padding: "8px 32px",
              borderRadius: 999,
              background: "#e2405f",
            }}
          >
            {scene.subtitle}
          </div>
        )}
        {scene.title && <div style={{ fontSize: 150, fontWeight: 900, marginTop: 24, lineHeight: 1.1 }}>{scene.title}</div>}
      </div>
      <Caption text={scene.text} translation={scene.translation} visible={talking > -0.2} />
      {voice && (
        <Sequence from={Math.round(LEAD_IN * fps)}>
          <Audio src={staticFile(voice)} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};

type GestureState = {
  current?: string;
  previous?: string;
  /** Video frame the current gesture began on. */
  startFrame: number;
};

const Avatar: React.FC<{
  avatar: IntroProps["avatar"];
  frame: number;
  fps: number;
  mouth: keyof IntroProps["avatar"]["layers"]["mouth"];
  gesture: GestureState;
  smiling: boolean;
}> = ({ avatar, frame, fps, mouth, gesture, smiling }) => {
  const [w, h] = avatar.size;
  const scale = 1040 / h;
  const height = h * scale;
  const base = `avatars/${avatar.folder}/`;
  const layer = (file: string, style?: React.CSSProperties) => (
    <Img
      key={file}
      src={staticFile(base + file)}
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", ...style }}
    />
  );
  const eyes =
    smiling && avatar.layers.eyes_happy
      ? avatar.layers.eyes_happy
      : blinking(frame, fps)
        ? avatar.layers.eyes_closed
        : avatar.layers.eyes_open;
  const box: React.CSSProperties = { position: "relative", width: w * scale, height };

  const rig = avatar.rig;
  if (!rig) {
    // One still picture: breathe and sway the whole of it.
    const bob = Math.sin((frame / fps) * Math.PI * 0.9) * 8;
    const sway = Math.sin((frame / fps) * Math.PI * 0.45) * 1.5;
    return (
      <div style={{ ...box, transform: `translateY(${bob}px) rotate(${sway}deg)`, transformOrigin: "50% 100%" }}>
        {avatar.layers.body && layer(avatar.layers.body)}
        {layer(eyes)}
        {layer(avatar.layers.mouth[mouth])}
      </div>
    );
  }

  const [nx, ny] = rig.neck;
  const speaking = mouth !== "n";

  // Breathing: the torso stretches from the hips (scaleY); whatever sits on
  // it (arms at the shoulders, the head at the neck) rides up with it.
  const breathe = 1 + Math.sin(frame / 22) * 0.012;
  const lift = (yFraction: number) => -(breathe - 1) * height * (1 - yFraction);

  // A gesture change is a beat, not a cut: the arms dip and spring back while
  // the old pose fades out over 3 frames, the body dips a little with them.
  const since = frame - gesture.startFrame;
  const swap = spring({ frame: since, fps, config: { damping: 14, stiffness: 220 } });
  const armBounce = gesture.previous ? (1 - swap) * 14 : 0;
  const bodyDip = gesture.previous ? (1 - swap) * 6 : 0;
  const fadeIn = gesture.previous ? Math.min(1, Math.max(0, since / 3)) : 1;
  const arms = rig.arms[gesture.current ?? ""] ?? Object.values(rig.arms)[0];
  const previousArms = gesture.previous ? rig.arms[gesture.previous] : undefined;

  // Head: slow tilt, leaning with the gesture, a small nod while speaking.
  const headTilt = Math.sin(frame / 28) * 2.5 + (gesture.current === "tip" ? -2 : gesture.current ? 1.5 : 0);
  const nod = speaking ? Math.sin(frame * 0.6) * 1.5 : 0;
  const hairRotate = Math.sin((frame - 6) / 30) * 3.5;

  // A glance towards the board (on her left, the viewer's right) for a second
  // after she starts presenting it, then back to the learners.
  const presenting = ["explain", "point", "pointer"].includes(gesture.current ?? "");
  const glance = presenting
    ? interpolate(since, [0, 6, fps * 0.9, fps * 1.2], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : 0;
  const glanceX = glance * 5;

  const shoulderY = lift(0.425) + bodyDip;
  return (
    <div style={box}>
      {rig.hair_back &&
        layer(rig.hair_back, {
          transform: `translateY(${lift(ny) + bodyDip}px) rotate(${hairRotate}deg)`,
          transformOrigin: `${nx * 100}% ${ny * 100 - 10}%`,
        })}
      {layer(rig.torso, {
        transform: `translateY(${bodyDip}px) scaleY(${breathe})`,
        transformOrigin: "50% 100%",
      })}
      {/* The old pose stays solid underneath until the new one, fading in
          on top, has covered it: no see-through arms mid-swap. */}
      {previousArms && fadeIn < 1 && layer(previousArms, { transform: `translateY(${shoulderY}px)` })}
      {arms && layer(arms, { opacity: fadeIn, transform: `translateY(${shoulderY + armBounce}px)` })}
      {rig.shoulders && layer(rig.shoulders, { transform: `translateY(${shoulderY}px)` })}
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translateY(${lift(ny) + bodyDip + nod}px) rotate(${headTilt}deg)`,
          transformOrigin: `${nx * 100}% ${ny * 100}%`,
        }}
      >
        {layer(rig.head)}
        {layer(eyes, { transform: `translateX(${glanceX}px)` })}
        {layer(avatar.layers.mouth[mouth])}
      </div>
    </div>
  );
};

/** The gesture at `seconds` of speech: the last one started by then. */
export function gestureAt(gestures: { at: number; gesture: string }[] | undefined, seconds: number): string | undefined {
  return gestureTimeline(gestures, seconds, 0, 1).current;
}

/** The current gesture, the one before it, and the frame it started on. */
export function gestureTimeline(
  gestures: { at: number; gesture: string }[] | undefined,
  seconds: number,
  leadIn: number,
  fps: number,
): GestureState {
  const sorted = [...(gestures ?? [])].sort((a, b) => a.at - b.at);
  let state: GestureState = { startFrame: 0 };
  for (const g of sorted) {
    if (g.at > seconds) break;
    state = { current: g.gesture, previous: state.current, startFrame: Math.round((leadIn + g.at) * fps) };
  }
  return state;
}

/** Anime sticker effects (💡 💧 ✨ ❗) popping beside her head. */
const Effects: React.FC<{
  avatar: IntroProps["avatar"];
  effects: { at: number; type: string; duration?: number }[];
  frame: number;
  fps: number;
}> = ({ avatar, effects, frame, fps }) => {
  const [w, h] = avatar.size;
  const scale = 1040 / h;
  return (
    <>
      {effects.map((effect, i) => {
        const file = avatar.fx?.[effect.type];
        const start = Math.round((LEAD_IN + effect.at) * fps);
        const end = start + Math.round((effect.duration ?? 1.6) * fps);
        if (!file || frame < start || frame > end + 8) return null;
        const pop = spring({ frame: frame - start, fps, config: { damping: 12, stiffness: 180 } });
        const out = interpolate(frame, [end, end + 8], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const bob = Math.sin((frame - start) / 6) * 4;
        return (
          <Img
            key={i}
            src={staticFile(`avatars/${avatar.folder}/${file}`)}
            style={{
              position: "absolute",
              // Up and to the right of her head.
              left: w * scale * 0.64,
              top: h * scale * 0.04 + bob,
              width: 150,
              transform: `scale(${pop})`,
              opacity: Math.min(1, pop * 1.5) * out,
            }}
          />
        );
      })}
    </>
  );
};

/** Blinks every 2.5–4 s for about 0.12 s, the same way on every render. */
function blinking(frame: number, fps: number): boolean {
  const t = frame / fps;
  let next = 1.6;
  let i = 0;
  while (next <= t) {
    if (t < next + 0.12) return true;
    i += 1;
    next += 2.5 + ((i * 7919) % 15) / 10;
  }
  return false;
}

const Caption: React.FC<{ text: string; translation?: string; visible: boolean }> = ({
  text,
  translation,
  visible,
}) => (
  <div
    style={{
      position: "absolute",
      // Right of the avatar, under the title card, so it never covers her.
      left: 960,
      right: 80,
      bottom: 90,
      display: "flex",
      justifyContent: "center",
      opacity: visible ? 1 : 0,
      fontFamily: '"Noto Sans CJK JP", "Noto Sans JP", sans-serif',
    }}
  >
    <div
      style={{
        padding: "20px 36px",
        borderRadius: 24,
        background: "rgba(10, 14, 30, .72)",
        color: "#fff",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 44, lineHeight: 1.55 }}>{text}</div>
      {translation && <div style={{ fontSize: 32, lineHeight: 1.45, color: "#ffe58a", marginTop: 8 }}>{translation}</div>}
    </div>
  </div>
);

/** Sakura petals drifting down, placed the same on every render. */
const Petals: React.FC<{ frame: number; width: number; height: number }> = ({ frame, width, height }) => {
  const petals = Array.from({ length: 24 }, (_, i) => {
    const seed = (i * 9301 + 49297) % 233280;
    const x = (seed / 233280) * width;
    const speed = 1.2 + (i % 5) * 0.35;
    const y = ((frame * speed + i * 97) % (height + 120)) - 60;
    const drift = Math.sin((frame + i * 30) / 40) * 40;
    const size = 18 + (i % 4) * 6;
    const spin = interpolate(frame, [0, 300], [0, 360 * (i % 2 ? 1 : -1)], { extrapolateRight: "extend" });
    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: x + drift,
          top: y,
          width: size,
          height: size * 0.7,
          borderRadius: "80% 0 80% 0",
          background: "#ffc0d4",
          opacity: 0.75,
          transform: `rotate(${spin}deg)`,
        }}
      />
    );
  });
  return <>{petals}</>;
};
