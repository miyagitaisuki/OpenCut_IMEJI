import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { practiceTiming } from "./practice";
import { Backdrop, C, FONT, Jp, Pop, SHADOW, TONES } from "./theme";
import { SHORTS } from "./shorts";
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
  /** A practice question after the examples: shown full screen from `at` for `length` seconds. */
  practice?: {
    question: string;
    options: string[];
    answer: number;
    explain?: string;
    think: number;
    at: number;
    length: number;
  };
};

/** A vertical 1080x1920 clip about one grammar point: the pattern, its examples as they are read,
 *  then (when given) one practice question with its countdown and answer. */
export const Short: React.FC<ShortProps> = ({ title, badge, parts, join = "+", note, items, footer, practice }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sec = frame / fps;
  const current = items.reduce((cur, it, i) => (sec >= it.at ? i : cur), -1);
  const tones = ["pink", "sky", "mint", "sun", "navy"] as const;
  const inPractice = practice !== undefined && sec >= practice.at;
  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <Backdrop />
      {/* the top and bottom covers of the Shorts interface: see shorts.ts */}
      {inPractice && practice ? (
        <PracticeCard practice={practice} t={sec - practice.at} />
      ) : (
        <div style={{ position: "absolute", left: SHORTS.margin, right: SHORTS.margin, top: SHORTS.contentTop, display: "flex", flexDirection: "column", gap: 34 }}>
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
      )}
      {footer && !inPractice ? <div style={{ position: "absolute", left: 0, right: 0, bottom: SHORTS.footerBottom, textAlign: "center", fontSize: 32, fontWeight: 700, color: C.rose }}>{footer}</div> : null}
    </AbsoluteFill>
  );
};

/** The practice question, full screen: choices pop in, a countdown runs, then the right one turns green. */
const PracticeCard: React.FC<{ practice: NonNullable<ShortProps["practice"]>; t: number }> = ({ practice, t }) => {
  const { countFrom, reveal } = practiceTiming(practice.length, practice.think, practice.options.length);
  const shown = t >= reveal;
  const remaining = Math.max(0, Math.ceil(reveal - t));
  // Pop times are on the clip's own timeline; t is measured from the start of this card.
  const base = practice.at;
  return (
    <div style={{ position: "absolute", left: SHORTS.practiceMargin, right: SHORTS.practiceMargin, top: SHORTS.practiceTop, display: "flex", flexDirection: "column", gap: 40 }}>
      <Pop at={base} from="scale">
        <div style={{ alignSelf: "center", background: TONES.sky.bg, color: TONES.sky.fg, borderRadius: 30, padding: "12px 40px", border: `4px solid ${TONES.sky.line}`, boxShadow: SHADOW }}>
          <Jp text="れんしゅう" style={{ fontSize: 40, fontWeight: 800 }} />
        </div>
      </Pop>
      <Pop at={base + 0.2} from="scale">
        <div style={{ background: "#fff", borderRadius: 36, padding: "40px 46px", boxShadow: SHADOW, border: `4px solid ${C.pink}` }}>
          <Jp text={practice.question} style={{ fontSize: 52, fontWeight: 800, color: C.navy, lineHeight: 1.6 }} />
        </div>
      </Pop>
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        {practice.options.map((opt, i) => {
          const right = shown && i === practice.answer;
          const at = 0.35 + 0.45 * (i + 1);
          const tone = right ? TONES.mint : TONES.pink;
          return (
            <div key={i} style={{ visibility: t >= at - 0.05 ? "visible" : "hidden" }}>
              <Pop at={base + at} from="right">
                <div style={{ display: "flex", alignItems: "center", gap: 26, background: tone.bg, color: tone.fg, borderRadius: 28, padding: "22px 34px", border: `4px solid ${tone.line}`, boxShadow: SHADOW }}>
                  <span style={{ fontSize: 46, fontWeight: 800, color: C.rose }}>{String.fromCharCode(65 + i)}</span>
                  <Jp text={opt} style={{ fontSize: 46, fontWeight: 700 }} />
                  {right ? <span style={{ marginLeft: "auto", fontSize: 60, fontWeight: 800, color: "#1f8a4c" }}>✓</span> : null}
                </div>
              </Pop>
            </div>
          );
        })}
      </div>
      <div style={{ textAlign: "center", fontSize: 120, fontWeight: 800, color: C.rose, minHeight: 130 }}>
        {t >= countFrom && !shown ? remaining : ""}
      </div>
      {shown && practice.explain ? (
        <Pop at={base + reveal} from="scale">
          <div style={{ textAlign: "center", fontSize: 38, fontWeight: 700, color: C.navySoft, lineHeight: 1.6 }}>
            <Jp text={practice.explain} style={{ fontSize: 38, fontWeight: 700, color: C.navySoft }} />
          </div>
        </Pop>
      ) : null}
    </div>
  );
};
