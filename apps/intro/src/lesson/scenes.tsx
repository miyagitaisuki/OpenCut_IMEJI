import { Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { Accent } from "./Accent";
import { C, FIRST, FONT, Jp, Pop, SAFE, SHADOW, STAGGER, SceneFrame, TONES, useReveal } from "./theme";
import { practiceTiming } from "./practice";
import type { PracticeScene, ChartScene, CompareScene, DialogueScene, GrammarScene, ImageScene, KeywordScene, LessonScene, TitleScene } from "./types";

type P<T> = { scene: T; duration: number };

const at = (i: number) => FIRST + i * STAGGER;

export const Title: React.FC<P<TitleScene>> = ({ scene, duration }) => {
  const badge = useReveal(0.2);
  return (
    <SceneFrame duration={duration}>
      <div style={{ display: "flex", alignItems: "center", gap: 48 }}>
        {scene.badge ? (
          <div
            style={{
              width: 190,
              height: 190,
              borderRadius: "50%",
              background: `linear-gradient(135deg, ${C.rose}, ${C.pink})`,
              color: "#fff",
              fontSize: 80,
              fontWeight: 800,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: SHADOW,
              transform: `scale(${0.6 + 0.4 * badge}) rotate(${(1 - badge) * -25}deg)`,
              flexShrink: 0,
            }}
          >
            {scene.badge}
          </div>
        ) : null}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Pop at={0.15} from="left">
            <Jp text={scene.title} style={{ fontSize: 120, fontWeight: 800, color: C.navy, lineHeight: 1.25 }} />
          </Pop>
          {scene.subtitle ? (
            <Pop at={0.6} from="left">
              <Jp text={scene.subtitle} style={{ fontSize: 46, fontWeight: 500, color: C.muted }} />
            </Pop>
          ) : null}
        </div>
      </div>
    </SceneFrame>
  );
};

export const Grammar: React.FC<P<GrammarScene>> = ({ scene, duration }) => {
  const join = scene.join ?? "+";
  const n = scene.parts.length;
  const tones = ["pink", "sky", "mint", "sun", "navy"] as const;
  return (
    <SceneFrame duration={duration} title={scene.title}>
      <div style={{ display: "flex", flexDirection: "column", gap: 26, alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 26, flexWrap: "wrap", justifyContent: "center" }}>
          {scene.parts.map((p, i) => {
            const tone = TONES[p.tone ?? tones[i % tones.length]];
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 26 }}>
                <Pop at={at(i * 2)} from="scale">
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                    <div
                      style={{
                        background: tone.bg,
                        color: tone.fg,
                        borderRadius: 30,
                        padding: "24px 44px",
                        boxShadow: SHADOW,
                        border: `4px solid ${tone.line}`,
                      }}
                    >
                      <Jp text={p.text} style={{ fontSize: 74, fontWeight: 800 }} />
                    </div>
                    {p.label ? <Jp text={p.label} style={{ fontSize: 30, fontWeight: 600, color: C.muted }} /> : null}
                  </div>
                </Pop>
                {i < n - 1 ? (
                  <Pop at={at(i * 2 + 1)} from="scale">
                    <span style={{ fontSize: 64, fontWeight: 800, color: C.rose }}>{join}</span>
                  </Pop>
                ) : null}
              </div>
            );
          })}
        </div>
        {scene.result ? (
          <Pop at={at(n * 2)} from="up">
            <div style={{ display: "flex", alignItems: "center", gap: 26 }}>
              <span style={{ fontSize: 64, fontWeight: 800, color: C.rose }}>＝</span>
              <div style={{ background: "#fff", borderRadius: 30, padding: "22px 48px", boxShadow: SHADOW, border: `4px solid ${C.rose}` }}>
                <Jp text={scene.result.text} style={{ fontSize: 80, fontWeight: 800, color: C.navy }} />
              </div>
              {scene.result.label ? <Jp text={scene.result.label} style={{ fontSize: 32, color: C.muted, fontWeight: 600 }} /> : null}
            </div>
          </Pop>
        ) : null}
        {scene.note ? (
          <Pop at={at(n * 2 + 1)}>
            <Jp text={scene.note} style={{ fontSize: 38, color: C.navySoft, fontWeight: 500 }} />
          </Pop>
        ) : null}
      </div>
    </SceneFrame>
  );
};

const Column: React.FC<{ side: CompareScene["left"]; index: number; from: "left" | "right" }> = ({ side, index, from }) => {
  const tone = TONES[side.tone ?? (from === "left" ? "pink" : "sky")];
  return (
    <Pop at={at(index * 3)} from={from} style={{ flex: 1, minWidth: 0, alignSelf: "stretch" }}>
      <div style={{ height: "100%", background: "#fff", borderRadius: 36, boxShadow: SHADOW, overflow: "hidden", border: `4px solid ${tone.line}` }}>
        <div style={{ background: tone.bg, padding: "22px 36px" }}>
          <Jp text={side.title} style={{ fontSize: 54, fontWeight: 800, color: tone.fg }} />
        </div>
        <div style={{ padding: "26px 36px", display: "flex", flexDirection: "column", gap: 18 }}>
          {side.items.map((it, i) => (
            <Pop key={i} at={at(index * 3 + 1 + i)} from="up">
              <div style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
                <span style={{ color: tone.line, fontSize: 40, fontWeight: 800 }}>●</span>
                <Jp text={it} style={{ fontSize: 40, fontWeight: 500, color: C.ink }} />
              </div>
            </Pop>
          ))}
        </div>
      </div>
    </Pop>
  );
};

export const Compare: React.FC<P<CompareScene>> = ({ scene, duration }) => (
  <SceneFrame duration={duration} title={scene.title}>
    <div style={{ display: "flex", alignItems: "stretch", gap: 26, alignSelf: "stretch" }}>
      <Column side={scene.left} index={0} from="left" />
      <Pop at={at(1)} from="scale" style={{ alignSelf: "center" }}>
        <div
          style={{
            width: 96,
            height: 96,
            borderRadius: "50%",
            background: C.navy,
            color: "#fff",
            fontSize: 38,
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: SHADOW,
          }}
        >
          VS
        </div>
      </Pop>
      <Column side={scene.right} index={1} from="right" />
    </div>
  </SceneFrame>
);

const IMAGE_W = [0, 900, 640, 500];
const IMAGE_H = [0, 330, 310, 280];

/** Pictures on cards that drift in slowly (Ken Burns), each with its caption. */
export const Picture: React.FC<P<ImageScene>> = ({ scene, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.min(3, Math.max(1, scene.images.length));
  const tone = TONES[scene.tone ?? "pink"];
  const w = IMAGE_W[n];
  const h = IMAGE_H[n];
  // Slow push in; capped so a long scene does not zoom on and on.
  const zoom = 1 + Math.min(0.08, (frame / fps) * 0.012);
  return (
    <SceneFrame duration={duration} title={scene.title}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
        <div style={{ display: "flex", gap: 28 }}>
          {scene.images.slice(0, 3).map((im, i) => (
            <Pop key={i} at={at(i)} from={i % 2 ? "right" : "left"}>
              <div style={{ width: w, background: "#fff", borderRadius: 30, border: `4px solid ${tone.line}`, boxShadow: SHADOW, overflow: "hidden" }}>
                <div style={{ width: w, height: h, overflow: "hidden", background: tone.bg }}>
                  <Img src={im.src.startsWith("http") ? im.src : staticFile(im.src)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
                </div>
                {im.caption ? (
                  <div style={{ padding: "12px 20px 16px", textAlign: "center" }}>
                    <Jp text={im.caption} style={{ fontSize: 34, fontWeight: 700, color: C.navy }} />
                  </div>
                ) : null}
              </div>
            </Pop>
          ))}
        </div>
        {scene.note ? <Jp text={scene.note} style={{ fontSize: 30, fontWeight: 600, color: C.navySoft }} /> : null}
      </div>
    </SceneFrame>
  );
};

const PALETTE = [C.pink, C.sky, C.mint, C.sun, "#e3d0ff"];

export const Chart: React.FC<P<ChartScene>> = ({ scene, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const grow = useReveal(FIRST);
  const max = Math.max(...scene.items.map((i) => i.value), 1);
  const total = scene.items.reduce((n, i) => n + i.value, 0) || 1;
  const unit = scene.unit ?? "";
  const pulse = 1 + 0.025 * Math.sin((frame / fps) * 4);

  if (scene.kind === "donut") {
    const R = 220;
    const r = 130;
    const circumference = 2 * Math.PI * ((R + r) / 2);
    let acc = 0;
    return (
      <SceneFrame duration={duration} title={scene.title}>
        <div style={{ display: "flex", alignItems: "center", gap: 70, justifyContent: "center" }}>
          <svg width={R * 2 + 20} height={R * 2 + 20} viewBox={`${-R - 10} ${-R - 10} ${R * 2 + 20} ${R * 2 + 20}`}>
            {scene.items.map((it, i) => {
              const frac = (it.value / total) * grow;
              const len = frac * circumference;
              const offset = -acc * circumference;
              acc += it.value / total;
              const hot = scene.highlight === i;
              return (
                <circle
                  key={i}
                  r={(R + r) / 2}
                  fill="none"
                  stroke={PALETTE[i % PALETTE.length]}
                  strokeWidth={(R - r) * (hot ? pulse : 1)}
                  strokeDasharray={`${Math.max(len - 3, 0)} ${circumference}`}
                  strokeDashoffset={offset}
                  transform="rotate(-90)"
                />
              );
            })}
            <text textAnchor="middle" y={16} fontSize={64} fontWeight={800} fill={C.navy} fontFamily="sans-serif">
              {Math.round(total)}
              {unit}
            </text>
          </svg>
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {scene.items.map((it, i) => (
              <Pop key={i} at={at(i)} from="right">
                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                  <div style={{ width: 34, height: 34, borderRadius: 10, background: PALETTE[i % PALETTE.length] }} />
                  <Jp
                    text={`${it.label}　${it.value}${unit}`}
                    style={{ fontSize: 44, fontWeight: scene.highlight === i ? 800 : 500, color: C.ink }}
                  />
                </div>
              </Pop>
            ))}
          </div>
        </div>
      </SceneFrame>
    );
  }

  return (
    <SceneFrame duration={duration} title={scene.title}>
      <div style={{ display: "flex", flexDirection: "column", gap: 26, width: "100%", paddingRight: 120 }}>
        {scene.items.map((it, i) => {
          const t = useReveal(at(i));
          const w = interpolate(it.value / max, [0, 1], [0, 100]) * t;
          const hot = scene.highlight === i;
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 24, opacity: Math.min(1, t * 1.5) }}>
              <Jp text={it.label} style={{ width: 260, fontSize: 42, fontWeight: hot ? 800 : 500, color: C.ink, textAlign: "right" }} />
              <div style={{ flex: 1, background: "#fff", borderRadius: 22, height: 62, boxShadow: SHADOW, overflow: "hidden" }}>
                <div
                  style={{
                    width: `${w}%`,
                    height: "100%",
                    borderRadius: 22,
                    background: hot ? `linear-gradient(90deg, ${C.rose}, ${C.pink})` : `linear-gradient(90deg, ${C.sky}, ${C.mint})`,
                  }}
                />
              </div>
              <span style={{ width: 150, fontSize: 44, fontWeight: 800, color: C.navy, fontFamily: FONT }}>
                {Math.round(it.value * t)}
                {unit}
              </span>
            </div>
          );
        })}
      </div>
    </SceneFrame>
  );
};

export const Dialogue: React.FC<P<DialogueScene>> = ({ scene, duration }) => {
  if (scene.layout === "timeline") {
    const n = scene.lines.length;
    return (
      <SceneFrame duration={duration} title={scene.title}>
        <div style={{ position: "relative", display: "flex", justifyContent: "space-between", gap: 24, paddingTop: 30, width: "100%" }}>
          <div style={{ position: "absolute", left: 60, right: 60, top: 78, height: 8, borderRadius: 4, background: C.pink }} />
          {scene.lines.map((l, i) => (
            <Pop key={i} at={at(i)} from="up" style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 22 }}>
              <div
                style={{
                  width: 96,
                  height: 96,
                  borderRadius: "50%",
                  background: i === n - 1 ? C.rose : C.navy,
                  color: "#fff",
                  fontSize: 52,
                  fontWeight: 800,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: SHADOW,
                  zIndex: 1,
                }}
              >
                {i + 1}
              </div>
              <div style={{ background: "#fff", borderRadius: 26, padding: "20px 24px", boxShadow: SHADOW, textAlign: "center" }}>
                {l.who ? <Jp text={l.who} style={{ fontSize: 36, color: C.muted, fontWeight: 600 }} /> : null}
                <div>
                  <Jp text={l.text} style={{ fontSize: 52, fontWeight: 700, color: C.ink }} />
                </div>
              </div>
            </Pop>
          ))}
        </div>
      </SceneFrame>
    );
  }
  return (
    <SceneFrame duration={duration} title={scene.title}>
      <div style={{ display: "flex", flexDirection: "column", gap: 22, width: "100%" }}>
        {scene.lines.map((l, i) => {
          const right = (l.side ?? (i % 2 ? "right" : "left")) === "right";
          return (
            <Pop key={i} at={at(i)} from={right ? "right" : "left"} style={{ alignSelf: right ? "flex-end" : "flex-start", maxWidth: "78%" }}>
              <div style={{ display: "flex", flexDirection: right ? "row-reverse" : "row", alignItems: "center", gap: 18 }}>
                {l.who ? (
                  <div
                    style={{
                      minWidth: 84,
                      height: 84,
                      borderRadius: "50%",
                      background: right ? C.sky : C.pink,
                      color: C.ink,
                      fontSize: 30,
                      fontWeight: 800,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: "0 10px",
                      boxShadow: SHADOW,
                    }}
                  >
                    {l.who}
                  </div>
                ) : null}
                <div
                  style={{
                    background: right ? C.navy : "#fff",
                    color: right ? "#fff" : C.ink,
                    borderRadius: right ? "34px 34px 8px 34px" : "34px 34px 34px 8px",
                    padding: "20px 34px",
                    boxShadow: SHADOW,
                  }}
                >
                  <Jp text={l.text} style={{ fontSize: 46, fontWeight: 600 }} />
                </div>
              </div>
            </Pop>
          );
        })}
      </div>
    </SceneFrame>
  );
};

export const Keyword: React.FC<P<KeywordScene>> = ({ scene, duration }) => (
  <SceneFrame duration={duration}>
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 26 }}>
      <Pop at={0.1} from="scale">
        <div
          style={{
            background: "#fff",
            borderRadius: 48,
            padding: "30px 80px",
            boxShadow: SHADOW,
            border: `5px solid ${C.pink}`,
            maxWidth: SAFE.width,
          }}
        >
          <Jp text={scene.keyword} style={{ fontSize: Math.round(Math.max(72, Math.min(130, (130 * 11) / Math.max(1, [...scene.keyword.replace(/\{[^}]*\}/g, "")].length)))), fontWeight: 800, color: C.navy }} />
        </div>
      </Pop>
      {scene.caption ? (
        <Pop at={0.5}>
          <div style={{ fontSize: 36, color: C.muted, fontWeight: 500, textAlign: "center", maxWidth: 1100, lineHeight: 1.4 }}>
            {scene.caption}
          </div>
        </Pop>
      ) : null}
    </div>
  </SceneFrame>
);

const LETTERS = ["A", "B", "C", "D"];

/** Question and choices, a ring counting down, then the right choice lights up. */
export const Practice: React.FC<P<PracticeScene>> = ({ scene, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sec = frame / fps;
  const { countFrom, reveal } = practiceTiming(duration, scene.think ?? 5, scene.options.length);
  const shown = useReveal(reveal);
  const left = Math.max(0, Math.ceil(reveal - sec));
  const ring = interpolate(sec, [countFrom, reveal], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const R = 46;
  const L = 2 * Math.PI * R;
  return (
    <SceneFrame duration={duration} title={scene.title}>
      <div style={{ display: "flex", flexDirection: "column", gap: 26, alignItems: "center", width: "100%" }}>
        <Pop at={FIRST} from="up">
          <Jp text={scene.question} style={{ fontSize: 60, fontWeight: 800, color: C.navy }} />
        </Pop>
        <div style={{ display: "flex", gap: 30, alignItems: "center", flexWrap: "wrap", justifyContent: "center" }}>
          {scene.options.map((o, i) => {
            const right = i === scene.answer;
            const dim = shown > 0.5 && !right;
            return (
              <Pop key={i} at={at(i + 1)} from="scale">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                    background: right && shown > 0.5 ? C.mint : "#fff",
                    border: `4px solid ${right && shown > 0.5 ? "#6fcaa5" : C.pink}`,
                    borderRadius: 30,
                    padding: "18px 36px",
                    boxShadow: SHADOW,
                    opacity: dim ? 0.45 : 1,
                    transform: `scale(${right ? 1 + 0.08 * shown : 1})`,
                  }}
                >
                  <span style={{ fontSize: 44, fontWeight: 800, color: C.rose }}>{LETTERS[i]}</span>
                  <Jp text={o} style={{ fontSize: 52, fontWeight: 700, color: C.ink }} />
                </div>
              </Pop>
            );
          })}
          {sec >= countFrom && sec < reveal ? (
            <svg width={112} height={112} viewBox="0 0 112 112">
              <circle cx={56} cy={56} r={R} fill="#fff" stroke={C.pinkSoft} strokeWidth={10} />
              <circle cx={56} cy={56} r={R} fill="none" stroke={C.rose} strokeWidth={10} strokeLinecap="round" strokeDasharray={L} strokeDashoffset={L * (1 - ring)} transform="rotate(-90 56 56)" />
              <text x={56} y={72} textAnchor="middle" fontSize={46} fontWeight={800} fill={C.navy} fontFamily={FONT}>{left}</text>
            </svg>
          ) : null}
        </div>
        {scene.explain && shown > 0.01 ? (
          <div style={{ opacity: shown }}>
            <Jp text={scene.explain} style={{ fontSize: 38, color: C.navySoft, fontWeight: 500 }} />
          </div>
        ) : null}
      </div>
    </SceneFrame>
  );
};

const Body: React.FC<{ scene: LessonScene; duration: number }> = ({ scene, duration }) => {
  switch (scene.template) {
    case "title":
      return <Title scene={scene} duration={duration} />;
    case "grammar":
      return <Grammar scene={scene} duration={duration} />;
    case "compare":
      return <Compare scene={scene} duration={duration} />;
    case "chart":
      return <Chart scene={scene} duration={duration} />;
    case "dialogue":
      return <Dialogue scene={scene} duration={duration} />;
    case "image":
      return <Picture scene={scene} duration={duration} />;
    case "practice":
      return (
        <>
          <Practice scene={scene} duration={duration} />
          <Accent kind="check" at={practiceTiming(duration, scene.think ?? 5, scene.options.length).reveal} />
        </>
      );
    case "keyword":
      return <Keyword scene={scene} duration={duration} />;
  }
};

/** A scene, with its accent sticker over it when the scene asks for one. */
export const SceneView: React.FC<{ scene: LessonScene; duration: number }> = ({ scene, duration }) => (
  <>
    <Body scene={scene} duration={duration} />
    {"accent" in scene && scene.accent ? <Accent kind={scene.accent} at={scene.accent_at ?? 0.8} /> : null}
  </>
);
