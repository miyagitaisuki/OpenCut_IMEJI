import { AbsoluteFill, Sequence, useVideoConfig } from "remotion";

import { SceneView } from "./scenes";
import { Backdrop } from "./theme";
import type { LessonProps } from "./types";

/**
 * The body of a lesson, without sound: a soft background and one scene per
 * stretch of cues. OpenCut lays the voice, subtitles and the chibi over it.
 */
export const Lesson: React.FC<LessonProps> = ({ segments }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Backdrop />
      {segments.map((s, i) => (
        <Sequence key={i} from={Math.round(s.start * fps)} durationInFrames={Math.max(1, Math.round((s.end - s.start) * fps))} premountFor={fps}>
          <SceneView scene={s.scene} duration={s.end - s.start} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
