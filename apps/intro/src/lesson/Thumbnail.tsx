import { AbsoluteFill, Img, staticFile } from "remotion";

import { Backdrop, C, FONT, Jp, SHADOW } from "./theme";

export type ThumbnailProps = {
  /** The big title, Japanese with furigana: `第{だい}5課{か}`. */
  title: string;
  /** A line under it (Vietnamese). */
  subtitle?: string;
  /** Round badge: `N5`. */
  badge?: string;
  /** A small tag at the top: `Minna no Nihongo`. */
  tag?: string;
  /** The chibi pose picture, relative to public/: `avatars/izumi/pose_c09.png`. */
  pose?: string;
};

/** A 1280x720 YouTube thumbnail: big title on the left, the chibi on the right. */
export const Thumbnail: React.FC<ThumbnailProps> = ({ title, subtitle, badge, tag, pose }) => {
  const plain = title.replace(/\{[^}]*\}/g, "");
  const size = Math.max(70, Math.min(150, Math.floor(620 / (Math.max(1, [...plain].length) * 1.05))));
  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <Backdrop />
      {pose ? (
        <Img src={staticFile(pose)} style={{ position: "absolute", right: -10, bottom: -20, height: 760, filter: "drop-shadow(0 12px 24px rgba(43,58,103,0.25))" }} />
      ) : null}
      <div style={{ position: "absolute", left: 64, top: 60, display: "flex", flexDirection: "column", gap: 26, width: 780 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
        {badge ? (
          <div
            style={{
              width: 100,
              height: 100,
              borderRadius: "50%",
              background: `linear-gradient(135deg, ${C.rose}, ${C.pink})`,
              color: "#fff",
              fontSize: 44,
              fontWeight: 800,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: SHADOW,
              flexShrink: 0,
            }}
          >
            {badge}
          </div>
        ) : null}
        {tag ? <div style={{ background: C.navy, color: "#fff", fontSize: 32, fontWeight: 700, borderRadius: 40, padding: "8px 28px" }}>{tag}</div> : null}
        </div>
        <div style={{ background: "#fff", borderRadius: 40, padding: "20px 44px", boxShadow: SHADOW, border: `6px solid ${C.pink}`, alignSelf: "flex-start" }}>
          <Jp text={title} style={{ fontSize: size, fontWeight: 800, color: C.navy, lineHeight: 1.35, whiteSpace: "nowrap" }} />
        </div>
        {subtitle ? <div style={{ fontSize: 50, fontWeight: 800, color: C.rose, lineHeight: 1.25, textShadow: "0 2px 0 #fff" }}>{subtitle}</div> : null}
      </div>
    </AbsoluteFill>
  );
};
