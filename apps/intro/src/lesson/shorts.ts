/**
 * The Shorts frame (1080 x 1920). The Shorts interface covers the top 130 px and the bottom 330 px
 * (title, like/share, the caption bar). Everything a viewer must read stays inside `safe`; the
 * footer sits just above the bottom cover. Kept in one place so every Short uses the same zone.
 */
export const SHORTS = {
  width: 1080,
  height: 1920,
  coveredTop: 130,
  coveredBottom: 330,
  /** Side margin of the grammar and examples column. */
  margin: 60,
  /** Top of the grammar column (below the top cover, with air). */
  contentTop: 150,
  /** Side margin and top of the practice question (a little narrower and lower). */
  practiceMargin: 70,
  practiceTop: 260,
  /** Bottom of the footer line (above the bottom cover). */
  footerBottom: 360,
} as const;
