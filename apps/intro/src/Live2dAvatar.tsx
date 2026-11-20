// A Live2D (Cubism 3/4) avatar for the intro, drawn with pixi-live2d-display.
//
// Remotion renders each frame on its own and may do them out of order, so
// nothing here keeps state between frames: the model's own clock (motions,
// physics, automatic blinking) is never run. Every frame sets the
// parameters it needs and draws, so the picture is a pure function of the
// frame number. Without physics, hair and clothes do not sway.
//
// Needs Live2D's Cubism Core (public/lib/live2dcubismcore.min.js, fetched
// by scripts/fetch-live2d-sample.ts: Live2D's licence does not let it live
// in this repository) and a model folder under public/avatars/.

import type { Live2DModel } from "pixi-live2d-display-advanced/cubism4";
import * as PIXI from "pixi.js";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

import type { VrmPoseState } from "./VrmAvatar";
import type { Mouth } from "./visemes";

export type Live2dConfig = {
  /** The `.model3.json` under public/avatars/<folder>/. */
  file: string;
  /** Zoom on top of "whole model fits the frame" (default 1). */
  zoom?: number;
  /** Where the model's centre sits, as fractions of the frame (default 0.5, 0.5). */
  center?: [number, number];
  /** Extra head tilt, in the model's own degrees (default 0). */
  tilt?: number;
};

/** ParamMouthOpenY / ParamMouthForm for each Japanese vowel (form: -1 round .. 1 wide). */
const MOUTH: Record<Mouth, { open: number; form: number }> = {
  a: { open: 1, form: 0.3 },
  i: { open: 0.3, form: 1 },
  u: { open: 0.35, form: -1 },
  e: { open: 0.55, form: 0.7 },
  o: { open: 0.75, form: -0.7 },
  n: { open: 0, form: 0 },
};

const CORE = "lib/live2dcubismcore.min.js";

function loadCore(): Promise<void> {
  if ((window as unknown as { Live2DCubismCore?: unknown }).Live2DCubismCore) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = staticFile(CORE);
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`cannot load ${CORE}: run \`bun run scripts/fetch-live2d-sample.ts\``));
    document.head.appendChild(script);
  });
}

type Loaded = { app: PIXI.Application; model: Live2DModel };

export const Live2dAvatar: React.FC<{
  folder: string;
  config: Live2dConfig;
  width: number;
  height: number;
  state: VrmPoseState;
}> = ({ folder, config, width, height, state }) => {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [handle] = useState(() => delayRender("loading the Live2D model"));

  useEffect(() => {
    let cancelled = false;
    let app: PIXI.Application | undefined;
    (async () => {
      await loadCore();
      // The plugin checks for the Cubism Core as it is imported, so it comes after the script.
      const { Live2DModel } = await import("pixi-live2d-display-advanced/cubism4");
      app = new PIXI.Application({
        view: canvas.current!,
        width,
        height,
        backgroundAlpha: 0,
        antialias: true,
        autoStart: false,
        preserveDrawingBuffer: true,
      });
      const model = await Live2DModel.from(staticFile(`avatars/${folder}/${config.file}`), { autoUpdate: false });
      if (cancelled) return;
      const zoom = config.zoom ?? 1;
      const fit = Math.min(width / model.internalModel.width, height / model.internalModel.height) * zoom;
      model.scale.set(fit);
      model.anchor.set(0.5, 0.5);
      const [cx, cy] = config.center ?? [0.5, 0.5];
      model.position.set(width * cx, height * cy);
      app.stage.addChild(model);
      setLoaded({ app, model });
      continueRender(handle);
    })().catch((error) => {
      throw error;
    });
    return () => {
      cancelled = true;
      app?.destroy(false);
    };
  }, [folder, config, width, height, handle]);

  // Runs before Remotion takes the picture, once the frame's state is known.
  useLayoutEffect(() => {
    if (!loaded) return;
    const { app, model } = loaded;
    const core = model.internalModel.coreModel as unknown as {
      setParameterValueById(id: string, value: number): void;
      update(): void;
    };
    const t = state.frame / state.fps;
    const set = (id: string, value: number) => {
      try {
        core.setParameterValueById(id, value);
      } catch {
        // A model without this parameter: skip it.
      }
    };
    const mouth = MOUTH[state.mouth];
    set("ParamMouthOpenY", mouth.open * state.mouthBlend);
    set("ParamMouthForm", mouth.form * state.mouthBlend);
    const eye = state.smiling ? 0.15 : state.blinking ? 0 : 1;
    set("ParamEyeLOpen", eye);
    set("ParamEyeROpen", eye);
    set("ParamEyeLSmile", state.smiling ? 1 : 0);
    set("ParamEyeRSmile", state.smiling ? 1 : 0);
    // Slow sway, breathing, a small nod while speaking.
    set("ParamAngleX", Math.sin(t * 0.8) * 6);
    set("ParamAngleY", Math.sin(t * 0.6) * 2 + (state.speaking ? Math.sin(t * 7.5) * 2 : 0));
    set("ParamAngleZ", Math.sin(t * 1.1) * 2 + (config.tilt ?? 0));
    set("ParamBodyAngleX", Math.sin(t * 0.8 - 0.4) * 3);
    set("ParamBodyAngleZ", Math.sin(t * 0.5) * 1.5);
    set("ParamBreath", (Math.sin(t * 1.9) + 1) / 2);
    set("ParamCheek", state.smiling ? 1 : 0);
    core.update();
    app.renderer.render(app.stage);
  }, [loaded, state.frame, state.fps, state.mouth, state.mouthBlend, state.blinking, state.smiling, state.speaking, config.tilt]);

  return <canvas ref={canvas} width={width} height={height} style={{ width, height }} />;
};
