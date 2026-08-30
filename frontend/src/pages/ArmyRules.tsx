import { useEffect, useState } from "react";
import { api } from "../api";
import { renderAbilityText } from "../markup";
import type { FactionArmyRules } from "../types";

export function ArmyRules() {
  const [factions, setFactions] = useState<FactionArmyRules[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.listArmyRules().then(setFactions).catch((e) => setError(String(e)));
  }, []);

  function toggle(faction: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(faction)) next.delete(faction);
      else next.add(faction);
      return next;
    });
  }

  return (
    <div className="page">
      <h1>Army Rules</h1>
      <p className="muted">
        Catalogue/library-level rules (Battle Focus, Blessings of Khorne, etc.) pulled straight
        from BSData — not yet tied to any roster or battle state, just reference text.
      </p>
      {error && <p className="error">{error}</p>}

      <ul className="army-rules-list">
        {factions.map((f) => (
          <li key={f.faction}>
            <button type="button" className="link-button faction-toggle" onClick={() => toggle(f.faction)}>
              {expanded.has(f.faction) ? "▾" : "▸"} <strong>{f.faction}</strong>{" "}
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
        ))}
        {factions.length === 0 && !error && <li className="muted">No army rules indexed yet.</li>}
      </ul>
    </div>
  );
}
