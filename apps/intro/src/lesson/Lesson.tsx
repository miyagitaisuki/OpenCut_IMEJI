import { linearTiming, type TransitionPresentation, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { AbsoluteFill, useVideoConfig } from "remotion";

import { Captions } from "./Captions";
import { SceneView } from "./scenes";
import { Backdrop } from "./theme";
import type { LessonProps } from "./types";

/** Seconds a scene change takes. The old scene stays under the new one for this long. */
export const TRANSITION = 0.5;

// Cycled by position, so neighbours never repeat and the lesson keeps its rhythm.
const PRESENTATIONS: (() => TransitionPresentation<Record<string, unknown>>)[] = [
  () => slide({ direction: "from-right" }) as TransitionPresentation<Record<string, unknown>>,
  () => fade() as TransitionPresentation<Record<string, unknown>>,
  () => wipe({ direction: "from-left" }) as TransitionPresentation<Record<string, unknown>>,
  () => slide({ direction: "from-bottom" }) as TransitionPresentation<Record<string, unknown>>,
  () => fade() as TransitionPresentation<Record<string, unknown>>,
  () => wipe({ direction: "from-top" }) as TransitionPresentation<Record<string, unknown>>,
];

/**
 * The body of a lesson, without sound: a soft background and one scene per
 * stretch of cues. OpenCut lays the voice, subtitles and the chibi over it.
 *
 * Scenes overlap while they change. To keep each one starting on its cue, a scene
 * is held `TRANSITION` seconds past its end; the overlap eats that time back, so
 * scene n+1 begins exactly at `segments[n+1].start`.
 */
export const Lesson: React.FC<LessonProps> = ({ segments, captions }) => {
  const { fps } = useVideoConfig();
  const T = Math.round(TRANSITION * fps);
  // Frames per scene, from the cue times rather than from rounded lengths, so errors do not add up.
  const startFrame = segments.map((s) => Math.round(s.start * fps));
  const endFrame = segments.map((s, i) => (i + 1 < segments.length ? startFrame[i + 1] : Math.round(s.end * fps)));
  return (
    <AbsoluteFill>
      <Backdrop />
      <TransitionSeries>
        {segments.flatMap((s, i) => {
          const last = i === segments.length - 1;
          const own = Math.max(1, endFrame[i] - startFrame[i]);
          // A scene shorter than its transition cannot overlap: it just cuts.
          const next = segments[i + 1] ? Math.max(1, endFrame[i + 1] - startFrame[i + 1]) : 0;
          const overlap = last ? 0 : Math.min(T, own, next);
          const items = [
            <TransitionSeries.Sequence key={`s${i}`} durationInFrames={own + overlap} premountFor={fps}>
              {/* A huge duration: the transition does the leaving, the scene's own fade-out stays out of the way. */}
              <SceneView scene={s.scene} duration={1e6} beats={s.beats} />
            </TransitionSeries.Sequence>,
          ];
          if (!last && overlap > 0) {
            items.push(
              <TransitionSeries.Transition
                key={`t${i}`}
                presentation={PRESENTATIONS[i % PRESENTATIONS.length]()}
                timing={linearTiming({ durationInFrames: overlap })}
              />,
            );
          }
          return items;
        })}
      </TransitionSeries>
      {captions?.length ? <Captions cues={captions} /> : null}
    </AbsoluteFill>
  );
};
