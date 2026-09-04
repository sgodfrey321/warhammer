export interface Ability {
  name: string;
  text: string;
}

export interface Weapon {
  name: string;
  range_type: "Ranged Weapons" | "Melee Weapons";
  characteristics: Record<string, string>;
}

export interface ModelProfile {
  name: string;
  stats: Record<string, string>;
  ranged_weapons: Weapon[];
  melee_weapons: Weapon[];
}

export interface UnitDefinition {
  id: string;
  faction: string;
  name: string;
  points_cost: number;
  // Smallest legal squad size (min models across points tiers); 0 if unknown. Used to
  // default the simulator's per-weapon firing counts.
  min_models: number;
  keywords: string[];
  // GW's "Battlefield Role" badge (Character, Battleline, Infantry, Vehicle, Epic Hero, ...).
  // null for a unit with no primary category in the source data.
  role: string | null;
  source_catalogue_id: string;
  source_entry_id: string;
  is_legends: boolean;
  stats: Record<string, string>;
  abilities: Ability[];
  rules: string[];
  weapons: Weapon[];
  model_profiles: ModelProfile[];
}

export const STAT_ORDER = ["M", "T", "Sv", "InSv", "W", "LD", "OC"] as const;
export const WEAPON_STAT_ORDER = ["Range", "A", "BS", "WS", "S", "AP", "D", "Keywords"] as const;

export interface Roster {
  id: number;
  name: string;
  faction: string;
  battle_size: string | null;
  points_limit: number | null;
  detachments: { name: string; dp: number }[];
  created_at: string;
  updated_at: string;
}

export interface LoadoutItem {
  name: string;
  count: number;
}

export interface ModelGroup {
  name: string;
  count: number;
}

export interface UnitBuff {
  label: string;
  stat: string;
  modifier: string;
}

export interface Unit {
  id: number;
  roster_id: number;
  unit_definition_id: string;
  quantity: number;
  notes: string | null;
  loadout: LoadoutItem[];
  model_groups: ModelGroup[];
  buffs: UnitBuff[];
}

export interface UnitOut extends Unit {
  unit_definition: UnitDefinition;
}

export interface RosterImportResult {
  roster: Roster;
  imported: string[];
  unmatched: string[];
  attachments_created: number;
}

export interface UnitSynergy {
  id: number;
  roster_id: number;
  source_unit_id: number;
  target_unit_id: number;
  trigger_phase: string;
  note: string | null;
}

export interface UnitAttachment {
  id: number;
  roster_id: number;
  leader_unit_id: number;
  led_unit_id: number;
}

export const PHASES = ["command", "movement", "shooting", "charge", "fight"] as const;
export type Phase = (typeof PHASES)[number];

export const DURATION_TYPES = [
  "end_of_phase",
  "end_of_turn",
  "end_of_battle_round",
  "until_next_command_phase",
  "until_condition_clears",
  "manual",
] as const;
export type DurationType = (typeof DURATION_TYPES)[number];

export interface PlayerState {
  id: number;
  battle_session_id: number;
  player_number: number;
  cp_gained: number;
  cp_spent: number;
  // Derived/cached server-side from mission-score tiers + vp_adjustment -- not directly settable.
  vp: number;
  vp_adjustment: number;
}

export interface MissionScore {
  player_number: number;
  section_index: number;
  tier_index: number;
  achieved_count: number;
}

export interface ActiveEffectOut {
  id: number;
  label: string;
  owner_player: number;
  duration_type: DurationType;
  created_at_step: number;
  lifts_restriction: string | null;
  unit_id: number | null;
  expired: boolean;
}

export const POOL_SCOPES = ["phase", "turn", "battle_round"] as const;
export type PoolScope = (typeof POOL_SCOPES)[number];

export interface DeclaredStatePool {
  id: number;
  roster_id: number;
  name: string;
  max_value: number;
  scope: PoolScope;
  stacking: boolean;
}

export interface PoolStateOut {
  pool_id: number;
  name: string;
  max_value: number;
  scope: PoolScope;
  owner_player: number;
  current_value: number;
}

export interface PoolEntryOut {
  id: number;
  pool_id: number;
  name: string;
  scope: PoolScope;
  owner_player: number;
  value: number;
  created_at_step: number;
}

export interface TurnStateOut {
  id: number;
  unit_id: number;
  battle_round: number;
  turn_owner: number;
  move_type: string | null;
  has_shot: boolean;
  has_charged: boolean;
  has_fought: boolean;
  is_fights_first: boolean;
  flags: string[];
  eligibility_warning: string | null;
}

export interface ArmyRule {
  name: string;
  text: string;
}

export interface FactionArmyRules {
  faction: string;
  rules: ArmyRule[];
}

export interface Detachment {
  name: string;
  rules: ArmyRule[];
}

export interface FactionDetachments {
  faction: string;
  detachments: Detachment[];
}

export const DISPOSITIONS = ["take-and-hold", "purge-the-foe", "reconnaissance", "priority-assets", "disruption"] as const;
export type Disposition = (typeof DISPOSITIONS)[number];

export const DISPOSITION_LABELS: Record<Disposition, string> = {
  "take-and-hold": "Take and Hold",
  "purge-the-foe": "Purge the Foe",
  reconnaissance: "Reconnaissance",
  "priority-assets": "Priority Assets",
  disruption: "Disruption",
};

export interface MissionTier {
  text: string;
  vp: number;
  per_unit: boolean;
  cumulative: boolean;
  kind: string | null;
}

export interface MissionSection {
  when: string;
  trigger: string | null;
  header_kind: string | null;
  tiers: MissionTier[];
}

export interface Mission {
  name: string;
  deck: Disposition;
  vs: Disposition;
  sections: MissionSection[];
}

export interface ActionRow {
  k: string;
  v: string;
}

export interface Action {
  title: string;
  rows: ActionRow[];
}

export interface SecondaryRow {
  text: string;
  vp: string;
  or_: boolean;
}

export interface SecondarySection {
  when: string;
  trigger: string | null;
  rows: SecondaryRow[];
}

export interface SecondaryMission {
  name: string;
  slug: string;
  when_drawn: string | null;
  action: Action | null;
  sections: SecondarySection[];
}

export interface SimulateOptions {
  half_range: boolean;
  charged: boolean;
  cover: boolean;
  hit_modifier: number;
  wound_modifier: number;
  reroll_hits: "none" | "ones" | "all";
  reroll_wounds: "none" | "ones" | "all";
  single_reroll_hit: boolean; // "re-roll one Hit roll" (e.g. Crystal Matrix) -- one failed die per volley
  single_reroll_wound: boolean;
  reroll_damage: boolean; // "re-roll the Damage roll" -- re-roll a below-average variable-damage result
  grant_sustained_hits: number; // keyword granted by an ability (e.g. Bladestorm), on top of the weapon's own
  grant_lethal_hits: boolean;
  grant_devastating_wounds: boolean;
  fnp: number | null; // the X in "Feel No Pain X+", e.g. 5 for 5+; null = none
  anti_active: boolean;
  anti_threshold: number | null;
  trials: number;
  seed: number | null;
}

export interface SimulateWeaponLine {
  weapon_characteristics: Record<string, string>;
  range_type: "Ranged Weapons" | "Melee Weapons";
  // How many copies of this weapon fire each trial (e.g. 4 Fusion guns = 4). The
  // weapon's own A is attacks PER copy.
  weapon_count: number;
}

export interface SimulateAttackerGroup {
  // One attacking unit's (possibly mixed) loadout plus its own options.
  weapons: SimulateWeaponLine[];
  options: SimulateOptions;
}

export interface SimulateRequest {
  // One or more attacking units firing into the same defender.
  attackers: SimulateAttackerGroup[];
  defender_stats: Record<string, string>;
  defender_model_count: number;
}

export interface DetectedEffect {
  ability_name: string;
  summary: string; // short label, e.g. "+1 to Hit"
  condition: string; // verbatim "While ..." clause, or "" if unconditional
  side: "attacker" | "defender";
  option_patch: Partial<SimulateOptions>; // merged into options when toggled on
  requires_target_keywords: string[]; // any-of target keywords this effect is gated on; [] = any target
}

export interface AnalyzeResponse {
  effects: DetectedEffect[];
}

export interface SimulateResponse {
  trials: number;
  weapon_count: number;
  total_wounds: number; // the target unit's whole wound pool (W * model_count)
  mean_damage: number;
  median_damage: number;
  damage_percentiles: Record<string, number>;
  damage_histogram: Record<string, number>; // wounds dealt -> trial count
  damage_at_least: Record<string, number>; // wounds threshold -> P(one round deals >= it)
  mean_models_slain: number;
  models_slain_histogram: Record<string, number>;
  p_at_least_one_kill: number;
  p_wipe: number;
  destroyed_by_round: Record<string, number>; // round N -> cumulative P(destroyed by end of N)
  median_rounds_to_destroy: number | null;
  per_unit: { mean_damage: number; mean_models_slain: number }[]; // per attacking unit, in the order sent
  damage_stack: Record<string, number[]>; // total wounds -> summed per-unit contribution (for the stacked chart)
}

export interface Layout {
  number: number;
  name: string;
  image: string;
  measurements_image: string;
}

export interface LayoutMatchup {
  deck: Disposition;
  vs: Disposition;
  name: string;
  layouts: Layout[];
}

export interface BattleOut {
  id: number;
  started_at: string;
  roster_id: number | null;
  opponent_roster_id: number | null;
  global_step: number;
  battle_round: number;
  active_player: number;
  current_phase: Phase;
  opponent_name: string | null;
  your_disposition: Disposition | null;
  opponent_disposition: Disposition | null;
  layout_number: number | null;
  players: PlayerState[];
  effects: ActiveEffectOut[];
  active_synergies: UnitSynergy[];
  turn_states: TurnStateOut[];
  pool_states: PoolStateOut[];
  pool_entries: PoolEntryOut[];
  mission_scores: MissionScore[];
}
