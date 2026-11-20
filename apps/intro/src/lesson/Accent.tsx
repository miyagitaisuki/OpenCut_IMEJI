import { Lottie, type LottieAnimationData } from "@remotion/lottie";
import { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, Sequence, staticFile, useVideoConfig } from "remotion";

import { SAFE } from "./theme";

const SIZE = 130;

/** A sticker (public/lottie/<kind>.json) that pops once, in the scene's top-right corner. */
export const Accent: React.FC<{ kind: string; at: number }> = ({ kind, at }) => {
  const { fps } = useVideoConfig();
  const [data, setData] = useState<LottieAnimationData | null>(null);
  const [handle] = useState(() => delayRender(`lottie ${kind}`));
  useEffect(() => {
    fetch(staticFile(`lottie/${kind}.json`))
      .then((r) => r.json())
      .then((json) => {
        setData(json);
        continueRender(handle);
      })
      .catch((e) => cancelRender(e));
  }, [kind, handle]);
  if (!data) return null;
  return (
    <Sequence from={Math.round(at * fps)} layout="none">
      <AbsoluteFill>
        <div style={{ position: "absolute", left: SAFE.left + SAFE.width - SIZE, top: SAFE.top - 20, width: SIZE, height: SIZE }}>
          <Lottie animationData={data} loop={false} style={{ width: SIZE, height: SIZE }} />
        </div>
      </AbsoluteFill>
    </Sequence>
  );
};
