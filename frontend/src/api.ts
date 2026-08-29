import type {
  ActiveEffectOut,
  BattleOut,
  PlayerState,
  Roster,
  RosterImportResult,
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

  searchUnitDefinitions: (search: string) =>
    request<UnitDefinition[]>(`/unit-definitions?search=${encodeURIComponent(search)}`),

  createBattle: (rosterId?: number) =>
    request<BattleOut>("/battles", { method: "POST", body: JSON.stringify({ roster_id: rosterId ?? null }) }),
  getBattle: (id: number) => request<BattleOut>(`/battles/${id}`),
  advancePhase: (id: number) => request<BattleOut>(`/battles/${id}/advance-phase`, { method: "PATCH" }),
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
};

export type { ActiveEffectOut };
