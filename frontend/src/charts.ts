// Validated with the dataviz skill's palette checker against this app's dark panel surface
// (#1e212b): single-series charts share one hue; the two-series charts use a pair that
// passes CVD/contrast checks. The app's original --accent (#c0392b) failed the
// contrast-vs-surface check, hence the lighter red here.
export const CHART_COLOR = "#e0574a";
export const CHART_COLOR_SECONDARY = "#4a90c9";

// Fixed hue order for the Strength/to-hit stacked charts (2+ best -> N/A worst), assigned by
// to-hit value never by rank, so the same value is always the same color.
export const SKILL_COLORS = ["#e0574a", "#4a90c9", "#d95926", "#199e70", "#9085e9"];

// Neutral "everything else" color, matching the app's --muted token so a folded "Other" segment
// reads as deliberately de-emphasized rather than as another hue.
export const OTHER_COLOR = "#8b8f9e";

// One color per attacking unit in the simulator's stacked damage chart.
export const SIM_UNIT_COLORS = ["#e0574a", "#5b9bd5", "#70ad47", "#ffc000", "#9b5bd5", "#43c6b8", "#e88b3a"];

// Shared bar-chart mark spec (dataviz skill: <=24px thick, 4px rounded data-end square at the
// baseline, solid recessive gridlines -- never dashed).
export const BAR_SIZE = 24;
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
