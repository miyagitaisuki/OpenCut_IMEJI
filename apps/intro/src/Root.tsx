import { Composition } from "remotion";

import { Intro, LEAD_IN, TAIL } from "./Intro";
import type { IntroProps } from "./types";
import { Lesson } from "./lesson/Lesson";
import { Short, type ShortProps } from "./lesson/Short";
import { Thumbnail, type ThumbnailProps } from "./lesson/Thumbnail";
import type { LessonProps } from "./lesson/types";
import sample from "../scenes/sample.props.json";

const FPS = 30;

const lessonDefaults: LessonProps = {
  duration: 6,
  segments: [{ start: 0, end: 6, cues: [0, 0], scene: { template: "keyword", keyword: "文法", caption: "Ngữ pháp" } }],
};

export const Root: React.FC = () => (
  <>
    <Composition
      id="Intro"
      component={Intro}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={150}
      defaultProps={sample as unknown as IntroProps}
      // As long as the voice, with a moment before and after.
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.ceil((LEAD_IN + Math.max(props.voiceSeconds, 2) + TAIL) * FPS),
      })}
    />
    <Composition
      id="Lesson"
      component={Lesson}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={FPS * 6}
      defaultProps={lessonDefaults}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.max(1, Math.ceil(props.duration * FPS)) })}
    />
    <Composition
      id="Thumbnail"
      component={Thumbnail}
      width={1280}
      height={720}
      fps={FPS}
      durationInFrames={1}
      defaultProps={{ title: "第{だい}5課{か}", subtitle: "Ngữ pháp", badge: "N5" } as ThumbnailProps}
    />
    <Composition
      id="Short"
      component={Short}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={FPS * 30}
      defaultProps={{ duration: 30, title: "Ngữ pháp", parts: [{ text: "A" }, { text: "B" }], items: [] } as ShortProps}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.max(1, Math.ceil(props.duration * FPS)) })}
    />
  </>
);
