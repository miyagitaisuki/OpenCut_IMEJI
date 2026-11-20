/** When a practice scene counts down and shows its answer, in seconds from the scene start. */
export function practiceTiming(duration: number, think = 5, optionsCount = 3): { countFrom: number; reveal: number } {
  // The question and its choices pop in first; the countdown starts once they are up.
  const countFrom = 0.35 + 0.45 * (optionsCount + 1);
  // The answer stays on screen at least 1.5 s before the scene ends.
  const latest = Math.max(countFrom, duration - 1.5);
  const reveal = Math.min(countFrom + Math.max(0, think), latest);
  return { countFrom, reveal };
}
