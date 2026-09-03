import { useState } from "react";
import { renderAbilityText } from "../markup";
import type { FactionDetachments } from "../types";

// One level deeper than ArmyRulesList (faction -> detachment -> rules, not faction -> rules) --
// a faction expands to its detachments, each of which expands to its own rule text.
export function DetachmentsList({ factions }: { factions: FactionDetachments[] }) {
  const [expandedFactions, setExpandedFactions] = useState<Set<string>>(new Set());
  const [expandedDetachments, setExpandedDetachments] = useState<Set<string>>(new Set());

  function toggleFaction(faction: string) {
    setExpandedFactions((prev) => {
      const next = new Set(prev);
      if (next.has(faction)) next.delete(faction);
      else next.add(faction);
      return next;
    });
  }

  function toggleDetachment(key: string) {
    setExpandedDetachments((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <ul className="army-rules-list">
      {factions.map((f) => (
        <li key={f.faction}>
          <button type="button" className="link-button faction-toggle" onClick={() => toggleFaction(f.faction)}>
            {expandedFactions.has(f.faction) ? "▾" : "▸"} <strong>{f.faction}</strong>{" "}
            <span className="muted">
              ({f.detachments.length} detachment{f.detachments.length === 1 ? "" : "s"})
            </span>
          </button>
          {expandedFactions.has(f.faction) && (
            <ul className="ability-list">
              {f.detachments.map((d) => {
                const key = `${f.faction}::${d.name}`;
                return (
                  <li key={d.name}>
                    <button type="button" className="link-button faction-toggle" onClick={() => toggleDetachment(key)}>
                      {expandedDetachments.has(key) ? "▾" : "▸"} <strong>{d.name}</strong>
                    </button>
                    {expandedDetachments.has(key) && (
                      <ul className="ability-list">
                        {d.rules.map((r) => (
                          <li key={r.name}>
                            <strong>{r.name}:</strong> {renderAbilityText(r.text, `${key}-${r.name}`)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </li>
      ))}
      {factions.length === 0 && <li className="muted">No detachments indexed yet.</li>}
    </ul>
  );
}
