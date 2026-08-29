export interface UnitDefinition {
  id: string;
  faction: string;
  name: string;
  points_cost: number;
  keywords: string[];
  source_catalogue_id: string;
  source_entry_id: string;
  is_legends: boolean;
}

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

export interface Unit {
  id: number;
  roster_id: number;
  unit_definition_id: string;
  quantity: number;
  notes: string | null;
}

export interface UnitOut extends Unit {
  unit_definition: UnitDefinition;
}

export interface RosterImportResult {
  roster: Roster;
  imported: string[];
  unmatched: string[];
}

export interface UnitSynergy {
  id: number;
  roster_id: number;
  source_unit_id: number;
  target_unit_id: number;
  trigger_phase: string;
  note: string | null;
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
}
