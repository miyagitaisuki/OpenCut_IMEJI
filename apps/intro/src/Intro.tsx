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

export const Intro: React.FC<IntroProps> = ({ scene, avatar, voice, visemes }) => {
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
          left: 120,
          bottom: -40,
          transform: `translateY(${(1 - enter) * 400}px)`,
        }}
      >
        <Avatar avatar={avatar} frame={frame} fps={fps} mouth={mouthAt(visemes, talking)} />
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

const Avatar: React.FC<{
  avatar: IntroProps["avatar"];
  frame: number;
  fps: number;
  mouth: keyof IntroProps["avatar"]["layers"]["mouth"];
}> = ({ avatar, frame, fps, mouth }) => {
  const [w, h] = avatar.size;
  const scale = 1000 / h;
  const base = `avatars/${avatar.folder}/`;
  // Breathing bob and a little sway, so she never stands frozen.
  const bob = Math.sin((frame / fps) * Math.PI * 0.9) * 8;
  const sway = Math.sin((frame / fps) * Math.PI * 0.45) * 1.5;
  const layer = (file: string) => (
    <Img src={staticFile(base + file)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
  );
  return (
    <div
      style={{
        position: "relative",
        width: w * scale,
        height: h * scale,
        transform: `translateY(${bob}px) rotate(${sway}deg)`,
        transformOrigin: "50% 100%",
      }}
    >
      {layer(avatar.layers.body)}
      {layer(blinking(frame, fps) ? avatar.layers.eyes_closed : avatar.layers.eyes_open)}
      {layer(avatar.layers.mouth[mouth])}
    </div>
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
      left: 860,
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
