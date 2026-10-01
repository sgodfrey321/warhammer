import { useState } from "react";
import { renderAbilityText } from "../markup";
import type { FactionArmyRules } from "../types";

// The user's own 5 main armies, pinned to the top of the list -- an original colored-initials
// badge per faction (no GW artwork/iconography reproduced), not the faction's own key art.
// Colors validated as a set (dataviz skill's palette checker) against this app's dark panel
// surface (#1e212b) in this exact order -- reordering these entries can reintroduce an
// adjacent-pair CVD/contrast failure, so re-run the validator if the order changes.
const PINNED_FACTIONS: { key: string; label: string; initials: string; badgeClass: string }[] = [
  { key: "Aeldari - Aeldari Library", label: "Aeldari", initials: "AE", badgeClass: "faction-badge-aeldari" },
  { key: "Library - Astartes Heresy Legends", label: "Space Marines", initials: "SM", badgeClass: "faction-badge-space-marines" },
  { key: "Chaos - Thousand Sons", label: "Thousand Sons", initials: "TS", badgeClass: "faction-badge-thousand-sons" },
  { key: "Chaos - Daemons Library", label: "Chaos Daemons", initials: "CD", badgeClass: "faction-badge-chaos-daemons" },
  { key: "Chaos - World Eaters", label: "World Eaters", initials: "WE", badgeClass: "faction-badge-world-eaters" },
];

function orderWithPinnedFirst(factions: FactionArmyRules[]): FactionArmyRules[] {
  const byKey = new Map(factions.map((f) => [f.faction, f]));
  const pinned = PINNED_FACTIONS.map((p) => byKey.get(p.key)).filter((f): f is FactionArmyRules => !!f);
  const pinnedKeys = new Set(pinned.map((f) => f.faction));
  const rest = factions.filter((f) => !pinnedKeys.has(f.faction));
  return [...pinned, ...rest];
}

// Shared by the standalone Army Rules page and the landing page's own "Army Rules" tab --
// same collapsible-by-faction presentation either way.
export function ArmyRulesList({ factions }: { factions: FactionArmyRules[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(faction: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(faction)) next.delete(faction);
      else next.add(faction);
      return next;
    });
  }

  const ordered = orderWithPinnedFirst(factions);

  return (
    <ul className="army-rules-list">
      {ordered.map((f) => {
        const pin = PINNED_FACTIONS.find((p) => p.key === f.faction);
        return (
          <li key={f.faction}>
            <button type="button" className="link-button faction-toggle" onClick={() => toggle(f.faction)}>
              {expanded.has(f.faction) ? "▾" : "▸"}{" "}
              {pin && <span className={`faction-badge ${pin.badgeClass}`}>{pin.initials}</span>}
              <strong>{f.faction}</strong>{" "}
              <span className="muted">
                ({f.rules.length} rule{f.rules.length === 1 ? "" : "s"})
              </span>
            </button>
            {expanded.has(f.faction) && (
              <ul className="ability-list">
                {f.rules.map((r) => (
                  <li key={r.name}>
                    <strong>{r.name}:</strong> {renderAbilityText(r.text, r.name)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
      {factions.length === 0 && <li className="muted">No army rules indexed yet.</li>}
    </ul>
  );
}
