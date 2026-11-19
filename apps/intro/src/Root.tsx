import { Composition } from "remotion";

import { Intro, LEAD_IN, TAIL } from "./Intro";
import type { IntroProps } from "./types";
import sample from "../scenes/sample.props.json";

const FPS = 30;

export const Root: React.FC = () => (
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
);
