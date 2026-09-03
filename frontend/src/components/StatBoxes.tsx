import { KeywordList } from "./Keyword";
import { STAT_ORDER, WEAPON_STAT_ORDER } from "../types";
import type { Weapon } from "../types";

// Shared by UnitsBrowser.tsx and RosterEditor.tsx's Available Units panel -- one boxed pill per
// stat/weapon characteristic, instead of a plain space-joined monospace string.
export function StatBoxes({ pairs }: { pairs: { label: string; value: React.ReactNode }[] }) {
  if (pairs.length === 0) return null;
  return (
    <span className="stat-boxes">
      {pairs.map((p) => (
        <span key={p.label} className="stat-box">
          <span className="stat-box-label">{p.label}</span>
          <span className="stat-box-value">{p.value}</span>
        </span>
      ))}
    </span>
  );
}

export function statPairs(stats: Record<string, string>): { label: string; value: string }[] {
  return STAT_ORDER.filter((k) => stats[k]).map((k) => ({ label: k, value: stats[k] }));
}

export function weaponPairs(w: Weapon): { label: string; value: React.ReactNode }[] {
  return WEAPON_STAT_ORDER.filter((k) => w.characteristics[k]).map((k) => ({
    label: k,
    value: k === "Keywords" ? <KeywordList value={w.characteristics[k]} /> : w.characteristics[k],
  }));
}
