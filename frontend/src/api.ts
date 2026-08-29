import type {
  ActiveEffectOut,
  BattleOut,
  DeclaredStatePool,
  PlayerState,
  Roster,
  RosterImportResult,
  TurnStateOut,
  UnitAttachment,
  UnitDefinition,
  UnitOut,
  UnitSynergy,
} from "./types";

const BASE_URL = "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${options?.method ?? "GET"} ${path} failed: ${resp.status} ${body}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const api = {
  listRosters: () => request<Roster[]>("/rosters"),
  getRoster: (id: number) => request<Roster>(`/rosters/${id}`),
  createRoster: (payload: { name: string; faction: string; points_limit?: number | null }) =>
    request<Roster>("/rosters", { method: "POST", body: JSON.stringify(payload) }),
  importRoster: (data: unknown) =>
    request<RosterImportResult>("/rosters/import", { method: "POST", body: JSON.stringify(data) }),

  listUnits: (rosterId: number) => request<UnitOut[]>(`/rosters/${rosterId}/units`),
  addUnit: (rosterId: number, payload: { unit_definition_id: string; quantity: number }) =>
    request<UnitOut>(`/rosters/${rosterId}/units`, { method: "POST", body: JSON.stringify(payload) }),
  deleteUnit: (rosterId: number, unitId: number) =>
    request<void>(`/rosters/${rosterId}/units/${unitId}`, { method: "DELETE" }),

  listSynergies: (rosterId: number) => request<UnitSynergy[]>(`/rosters/${rosterId}/synergies`),
  addSynergy: (
    rosterId: number,
    payload: { source_unit_id: number; target_unit_id: number; trigger_phase: string; note?: string },
  ) => request<UnitSynergy>(`/rosters/${rosterId}/synergies`, { method: "POST", body: JSON.stringify(payload) }),
  deleteSynergy: (rosterId: number, synergyId: number) =>
    request<void>(`/rosters/${rosterId}/synergies/${synergyId}`, { method: "DELETE" }),

  listAttachments: (rosterId: number) => request<UnitAttachment[]>(`/rosters/${rosterId}/attachments`),
  addAttachment: (rosterId: number, leaderUnitId: number, ledUnitId: number) =>
    request<UnitAttachment>(`/rosters/${rosterId}/attachments`, {
      method: "POST",
      body: JSON.stringify({ leader_unit_id: leaderUnitId, led_unit_id: ledUnitId }),
    }),
  deleteAttachment: (rosterId: number, attachmentId: number) =>
    request<void>(`/rosters/${rosterId}/attachments/${attachmentId}`, { method: "DELETE" }),

  listPools: (rosterId: number) => request<DeclaredStatePool[]>(`/rosters/${rosterId}/pools`),
  addPool: (
    rosterId: number,
    payload: { name: string; max_value: number; scope: string; stacking: boolean },
  ) => request<DeclaredStatePool>(`/rosters/${rosterId}/pools`, { method: "POST", body: JSON.stringify(payload) }),
  deletePool: (rosterId: number, poolId: number) =>
    request<void>(`/rosters/${rosterId}/pools/${poolId}`, { method: "DELETE" }),

  searchUnitDefinitions: (search: string) =>
    request<UnitDefinition[]>(`/unit-definitions?search=${encodeURIComponent(search)}`),

  createBattle: (rosterId?: number) =>
    request<BattleOut>("/battles", { method: "POST", body: JSON.stringify({ roster_id: rosterId ?? null }) }),
  listBattlesForRoster: (rosterId: number) => request<BattleOut[]>(`/battles?roster_id=${rosterId}`),
  getBattle: (id: number) => request<BattleOut>(`/battles/${id}`),
  advancePhase: (id: number) => request<BattleOut>(`/battles/${id}/advance-phase`, { method: "PATCH" }),
  retreatPhase: (id: number) => request<BattleOut>(`/battles/${id}/retreat-phase`, { method: "PATCH" }),
  updatePlayer: (
    battleId: number,
    playerNumber: number,
    payload: Partial<Pick<PlayerState, "cp_gained" | "cp_spent" | "vp">>,
  ) =>
    request<PlayerState>(`/battles/${battleId}/players/${playerNumber}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  addEffect: (
    battleId: number,
    payload: { label: string; owner_player: number; duration_type: string },
  ) => request<BattleOut>(`/battles/${battleId}/effects`, { method: "POST", body: JSON.stringify(payload) }),
  dismissEffect: (battleId: number, effectId: number) =>
    request<BattleOut>(`/battles/${battleId}/effects/${effectId}`, { method: "DELETE" }),

  acknowledgeSynergy: (battleId: number, synergyId: number) =>
    request<BattleOut>(`/battles/${battleId}/synergies/${synergyId}/acknowledge`, { method: "POST" }),

  spendPool: (battleId: number, poolId: number, amount = 1) =>
    request<BattleOut>(`/battles/${battleId}/pools/${poolId}/spend`, {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  addPoolEntry: (battleId: number, poolId: number, ownerPlayer: number, value: number) =>
    request<BattleOut>(`/battles/${battleId}/pools/${poolId}/add`, {
      method: "POST",
      body: JSON.stringify({ owner_player: ownerPlayer, value }),
    }),

  updateTurnState: (
    battleId: number,
    unitId: number,
    payload: Partial<Pick<TurnStateOut, "move_type" | "has_shot" | "has_charged" | "has_fought" | "is_fights_first">>,
  ) =>
    request<TurnStateOut>(`/battles/${battleId}/units/${unitId}/turn-state`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};

export type { ActiveEffectOut };
