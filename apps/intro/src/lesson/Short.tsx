import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { Backdrop, C, FONT, Jp, Pop, SHADOW, TONES } from "./theme";
import type { Tone } from "./types";

export type ShortProps = {
  /** Length in seconds (under 60 for a Short). */
  duration: number;
  title: string;
  badge?: string;
  parts: { text: string; label?: string; tone?: Tone }[];
  join?: "+" | "→";
  note?: string;
  /** Examples; `at` is when its sentence starts being read, in seconds. */
  items: { text: string; translation?: string; picture?: string; at: number }[];
  footer?: string;
};

/** A vertical 1080x1920 clip about one grammar point: the pattern, then its examples as they are read. */
export const Short: React.FC<ShortProps> = ({ title, badge, parts, join = "+", note, items, footer }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sec = frame / fps;
  const current = items.reduce((cur, it, i) => (sec >= it.at ? i : cur), -1);
  const tones = ["pink", "sky", "mint", "sun", "navy"] as const;
  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <Backdrop />
      {/* the top 130 px and bottom 330 px are covered by the Shorts interface */}
      <div style={{ position: "absolute", left: 60, right: 60, top: 150, display: "flex", flexDirection: "column", gap: 34 }}>
        <Pop at={0.1} from="left">
          <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
            {badge ? (
              <div style={{ width: 110, height: 110, borderRadius: "50%", background: `linear-gradient(135deg, ${C.rose}, ${C.pink})`, color: "#fff", fontSize: 48, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: SHADOW, flexShrink: 0 }}>
                {badge}
              </div>
            ) : null}
            <Jp text={title} style={{ fontSize: 66, fontWeight: 800, color: C.navy, lineHeight: 1.25 }} />
          </div>
        </Pop>
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", justifyContent: "center" }}>
          {parts.map((p, i) => {
            const tone = TONES[p.tone ?? tones[i % tones.length]];
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <Pop at={0.5 + i * 0.35} from="scale">
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                    <div style={{ background: tone.bg, color: tone.fg, borderRadius: 26, padding: "14px 30px", boxShadow: SHADOW, border: `4px solid ${tone.line}` }}>
                      <Jp text={p.text} style={{ fontSize: 58, fontWeight: 800 }} />
                    </div>
                    {p.label ? <Jp text={p.label} style={{ fontSize: 26, fontWeight: 600, color: C.muted }} /> : null}
                  </div>
                </Pop>
                {i < parts.length - 1 ? <span style={{ fontSize: 50, fontWeight: 800, color: C.rose }}>{join}</span> : null}
              </div>
            );
          })}
        </div>
        {note ? (
          <Pop at={0.8 + parts.length * 0.35}>
            <div style={{ textAlign: "center", fontSize: 34, fontWeight: 700, color: C.navySoft }}>{note}</div>
          </Pop>
        ) : null}
        <div style={{ display: "flex", flexDirection: "column", gap: 22, marginTop: 6 }}>
          {items.map((it, i) => (
            <div key={i} style={{ visibility: sec >= it.at - 0.05 ? "visible" : "hidden" }}>
              <Pop at={it.at} from="right">
                <div style={{ display: "flex", background: "#fff", borderRadius: 30, overflow: "hidden", boxShadow: SHADOW, border: `4px solid ${i === current ? C.rose : C.pink}`, height: 250 }}>
                  {it.picture ? <Img src={staticFile(it.picture)} style={{ width: 333, height: 250, objectFit: "cover", flexShrink: 0 }} /> : null}
                  <div style={{ padding: "12px 24px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 8, minWidth: 0 }}>
                    <Jp text={it.text} style={{ fontSize: 40, fontWeight: 800, color: C.navy, lineHeight: 1.7 }} />
                    {it.translation ? <span style={{ fontSize: 28, fontWeight: 500, color: C.muted }}>{it.translation}</span> : null}
                  </div>
                </div>
              </Pop>
            </div>
          ))}
        </div>
      </div>
      {footer ? <div style={{ position: "absolute", left: 0, right: 0, bottom: 360, textAlign: "center", fontSize: 32, fontWeight: 700, color: C.rose }}>{footer}</div> : null}
    </AbsoluteFill>
  );
};
