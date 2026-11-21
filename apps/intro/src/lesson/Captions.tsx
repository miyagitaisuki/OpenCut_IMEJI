import { AbsoluteFill, interpolate, interpolateColors, useCurrentFrame, useVideoConfig } from "remotion";

import { FONT } from "./theme";
import type { KaraokeCue, Unit } from "./types";

const SUNG = "#60a5fa"; // primary-400
const TEXT = "#ffffff";
/** Left of the chibi, which stands in the lower right. */
const AREA = { left: 60, width: 1380, bottom: 40 };

// A colour fade, not a clipped gradient: background-clip:text paints solid blocks on ruby.
const Lit: React.FC<{ text: string; progress: number; size: number; weight: number }> = ({ text, progress, size, weight }) => (
  <span style={{ fontSize: size, fontWeight: weight, color: interpolateColors(progress, [0, 1], [TEXT, SUNG]) }}>{text}</span>
);

const UnitView: React.FC<{ u: Unit; t: number }> = ({ u, t }) => {
  const progress = Math.max(0, Math.min(1, (t - u.start) / Math.max(0.01, u.end - u.start)));
  if (u.reading) {
    return (
      <ruby style={{ rubyAlign: "center" }}>
        <Lit text={u.base} progress={progress} size={56} weight={700} />
        <rt style={{ fontSize: 26, fontWeight: 600, letterSpacing: 0 }}>
          <Lit text={u.reading} progress={progress} size={26} weight={600} />
        </rt>
      </ruby>
    );
  }
  return <Lit text={u.base} progress={progress} size={56} weight={700} />;
};

/** The subtitle being spoken now, lit unit by unit, with its translation under it. */
export const Captions: React.FC<{ cues: KaraokeCue[] }> = ({ cues }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const cue = cues.find((c) => t >= c.start - 0.05 && t < c.end + 0.15);
  if (!cue) return null;
  const alpha = interpolate(t, [cue.start - 0.05, cue.start + 0.1, cue.end, cue.end + 0.15], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ fontFamily: FONT, opacity: alpha }}>
      <div style={{ position: "absolute", left: AREA.left, width: AREA.width, bottom: AREA.bottom, display: "flex", justifyContent: "center" }}>
        <div
          style={{
            background: "rgba(10,14,30,0.78)",
            borderRadius: 26,
            padding: "22px 40px 24px",
            maxWidth: AREA.width,
            textAlign: "center",
            boxShadow: "0 10px 30px rgba(10,14,30,0.25)",
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "flex-end", lineHeight: 1.7 }}>
            {cue.units.map((u, i) => (
              <UnitView key={i} u={u} t={t} />
            ))}
          </div>
          {cue.translation ? <div style={{ marginTop: 10, fontSize: 38, fontWeight: 500, color: "#ffd230" }}>{cue.translation}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
