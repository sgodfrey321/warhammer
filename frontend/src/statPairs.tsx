import { KeywordList } from "./components/Keyword";
import { STAT_ORDER, WEAPON_STAT_ORDER } from "./types";
import type { Weapon } from "./types";

export function statPairs(stats: Record<string, string>): { label: string; value: string }[] {
  return STAT_ORDER.filter((k) => stats[k]).map((k) => ({ label: k, value: stats[k] }));
}

export function weaponPairs(w: Weapon): { label: string; value: React.ReactNode }[] {
  return WEAPON_STAT_ORDER.filter((k) => w.characteristics[k]).map((k) => ({
    label: k,
    value: k === "Keywords" ? <KeywordList value={w.characteristics[k]} /> : w.characteristics[k],
  }));
}
