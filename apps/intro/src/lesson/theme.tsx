import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import type { Tone } from "./types";

/** Bảng màu IMEJI (tokens.css của hệ thống thiết kế IMEJI). Xem DESIGN.md. */
export const C = {
  cream: "#f8fafc", // slate-50
  pinkSoft: "#eff6ff", // primary-50
  pink: "#bfdbfe", // primary-200
  rose: "#60a5fa", // primary-400
  navy: "#1e3a8a", // primary-900
  navySoft: "#1d4ed8", // primary-700
  mint: "#d0fae5", // success-100
  sun: "#fef3c6", // warning-100
  sky: "#dbeafe", // primary-100
  ink: "#0f172a", // slate-900
  muted: "#526177", // slate-500
};

/** Tiêu đề dùng serif (IMEJI: Playfair Display; tiếng Nhật dùng Noto Serif JP). */
export const SERIF = '"Noto Serif JP", "Noto Serif CJK JP", "Playfair Display", serif';

export const FONT = '"Be Vietnam Pro", "Noto Sans CJK JP", "Noto Sans JP", "Yu Gothic", "Meiryo", sans-serif';

export const TONES: Record<Tone, { bg: string; fg: string; line: string }> = {
  pink: { bg: C.pink, fg: C.ink, line: C.rose },
  navy: { bg: C.navy, fg: "#ffffff", line: C.navySoft },
  mint: { bg: C.mint, fg: C.ink, line: "#34d399" }, // success-400
  sun: { bg: C.sun, fg: C.ink, line: "#ffb900" }, // warning-400
  sky: { bg: C.sky, fg: C.ink, line: "#60a5fa" }, // primary-400
};

/**
 * The area content may use: the top half. Burned-in subtitles (Japanese over
 * Vietnamese, up to ~7 lines) fill the bottom half, the chibi the lower right.
 * Content that is taller or wider than this is scaled down to fit (see `Fit`).
 */
export const SAFE = { left: 90, top: 50, width: 1740, height: 460 };

export const SHADOW = "0 18px 40px rgba(15, 23, 42, 0.14), 0 2px 6px rgba(15, 23, 42, 0.08)";

const RUBY = /([一-鿿々]+)\{([^}]+)\}/g;

/** Japanese text with furigana: `食{た}べる` -> 食 over た, then べる. */
export const Jp: React.FC<{ text: string; style?: CSSProperties }> = ({ text, style }) => {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(RUBY)) {
    const at = m.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    parts.push(
      <ruby key={at}>
        {m[1]}
        <rt style={{ fontSize: "0.42em", fontWeight: 500, letterSpacing: 0 }}>{m[2]}</rt>
      </ruby>,
    );
    last = at + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <span style={{ fontFamily: FONT, ...style }}>{parts}</span>;
};

/** 0 -> 1 with a soft spring, `at` seconds into the scene. */
export function useReveal(at: number): number {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - Math.round(at * fps), fps, config: { damping: 15, stiffness: 120 } });
}

/** Items appear one after another, as the voice goes on. */
export const STAGGER = 0.45;
export const FIRST = 0.35;

/** Pops up and slides in: wrap each item with it. */
export const Pop: React.FC<{ at: number; from?: "up" | "left" | "right" | "scale"; style?: CSSProperties; children: ReactNode }> = ({
  at,
  from = "up",
  style,
  children,
}) => {
  const t = useReveal(at);
  const d = (1 - t) * 48;
  const transform =
    from === "left" ? `translateX(${-d}px)` : from === "right" ? `translateX(${d}px)` : from === "scale" ? `scale(${0.7 + 0.3 * t})` : `translateY(${d}px)`;
  return <div style={{ opacity: Math.min(1, t * 1.4), transform, ...style }}>{children}</div>;
};

/** Scales its content down (never up) to fit `width` x `height`, and centres it. */
export const Fit: React.FC<{ width: number; height: number; children: ReactNode }> = ({ width, height, children }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ scale: 1, top: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.scrollWidth;
    const h = el.scrollHeight;
    const scale = Math.min(1, height / h, width / w);
    setFit({ scale, top: Math.max(0, (height - h * scale) / 2) });
  }, [width, height]);
  return (
    <div style={{ position: "relative", width, height }}>
      <div
        ref={ref}
        style={{ position: "absolute", left: 0, top: fit.top, width, transform: `scale(${fit.scale})`, transformOrigin: "top center" }}
      >
        {children}
      </div>
    </div>
  );
};

/** The scene's frame: slides in, fades out before the next one. */
export const SceneFrame: React.FC<{ duration: number; title?: string; children: ReactNode }> = ({ duration, title, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seconds = frame / fps;
  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 110 } });
  const out = interpolate(seconds, [duration - 0.3, duration], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ opacity: Math.min(1, enter * 1.5) * out }}>
      <div
        style={{
          position: "absolute",
          left: SAFE.left,
          top: SAFE.top,
          width: SAFE.width,
          height: SAFE.height,
          transform: `translateY(${(1 - enter) * 36}px)`,
          display: "flex",
          flexDirection: "column",
          gap: 22,
          fontFamily: FONT,
        }}
      >
        {title ? <Heading text={title} /> : null}
        <Fit width={SAFE.width} height={SAFE.height - (title ? 82 : 0)}>
          <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>{children}</div>
        </Fit>
      </div>
    </AbsoluteFill>
  );
};

const Heading: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
    <div style={{ width: 12, height: 52, borderRadius: 6, background: `linear-gradient(${C.rose}, ${C.pink})` }} />
    <Jp text={text} style={{ fontFamily: SERIF, fontSize: 52, fontWeight: 700, color: C.navy }} />
  </div>
);

/** Soft moving background shared by every scene. */
export const Backdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const blobs = [
    { x: 0.12, y: 0.18, r: 380, c: C.pink, s: 0.11 },
    { x: 0.82, y: 0.2, r: 320, c: C.sky, s: 0.09 },
    { x: 0.62, y: 0.8, r: 420, c: C.mint, s: 0.07 },
    { x: 0.25, y: 0.85, r: 300, c: C.sun, s: 0.1 },
  ];
  return (
    <AbsoluteFill style={{ background: `linear-gradient(150deg, ${C.cream} 0%, ${C.pinkSoft} 100%)`, overflow: "hidden" }}>
      {blobs.map((b, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: width * b.x + Math.sin(t * b.s * 6 + i) * 60 - b.r / 2,
            top: height * b.y + Math.cos(t * b.s * 5 + i * 2) * 50 - b.r / 2,
            width: b.r,
            height: b.r,
            borderRadius: "50%",
            background: b.c,
            opacity: 0.5,
            filter: "blur(70px)",
          }}
        />
      ))}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `radial-gradient(${C.navy}18 2px, transparent 2px)`,
          backgroundSize: "44px 44px",
          opacity: 0.5,
        }}
      />
    </AbsoluteFill>
  );
};
