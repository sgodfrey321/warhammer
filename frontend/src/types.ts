export interface Ability {
  name: string;
  text: string;
}

export interface Weapon {
  name: string;
  range_type: "Ranged Weapons" | "Melee Weapons";
  characteristics: Record<string, string>;
}

export interface UnitDefinition {
  id: string;
  faction: string;
  name: string;
  points_cost: number;
  keywords: string[];
  source_catalogue_id: string;
  source_entry_id: string;
  is_legends: boolean;
  stats: Record<string, string>;
  abilities: Ability[];
  weapons: Weapon[];
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

export interface Unit {
  id: number;
  roster_id: number;
  unit_definition_id: string;
  quantity: number;
  notes: string | null;
  loadout: LoadoutItem[];
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
  vp: number;
}

export interface ActiveEffectOut {
  id: number;
  label: string;
  owner_player: number;
  duration_type: DurationType;
  created_at_step: number;
  lifts_restriction: string | null;
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

export interface BattleOut {
  id: number;
  started_at: string;
  roster_id: number | null;
  global_step: number;
  battle_round: number;
  active_player: number;
  current_phase: Phase;
  players: PlayerState[];
  effects: ActiveEffectOut[];
  active_synergies: UnitSynergy[];
  turn_states: TurnStateOut[];
  pool_states: PoolStateOut[];
  pool_entries: PoolEntryOut[];
}
