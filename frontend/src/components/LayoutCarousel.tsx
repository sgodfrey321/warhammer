import { useState } from "react";
import type { LayoutMatchup } from "../types";

// One layout image at a time with prev/next -- the full set (2-3 per matchup) side by side
// was too dense to read at a glance. Keyed by matchup in the caller so the index resets
// whenever the selected matchup changes instead of carrying over a stale index.
export function LayoutCarousel({
  matchup,
  showMeasurements,
  children,
}: {
  matchup: LayoutMatchup;
  showMeasurements: boolean;
  // Rendered under the image, given the currently-displayed layout -- lets a caller (e.g.
  // the battle setup screen) add a "use this layout" action without this component knowing
  // about layout selection at all.
  children?: (layoutNumber: number) => React.ReactNode;
}) {
  const [index, setIndex] = useState(0);
  const layout = matchup.layouts[index];
  if (!layout) return null;

  return (
    <div className="layout-carousel">
      <div className="layout-carousel-nav">
        <button type="button" onClick={() => setIndex((i) => (i - 1 + matchup.layouts.length) % matchup.layouts.length)}>
          ‹
        </button>
        <span>
          {layout.name} ({index + 1} / {matchup.layouts.length})
        </span>
        <button type="button" onClick={() => setIndex((i) => (i + 1) % matchup.layouts.length)}>
          ›
        </button>
      </div>
      <img src={showMeasurements ? layout.measurements_image : layout.image} alt={layout.name} />
      {children?.(layout.number)}
    </div>
  );
}
