import type {
  ActiveEffectOut,
  AuthResponse,
  AuthUser,
  BattleOut,
  DeclaredStatePool,
  Disposition,
  FactionArmyRules,
  FactionDetachments,
  LayoutMatchup,
  Mission,
  PlayerState,
  Roster,
  RosterImportResult,
  AnalyzeResponse,
  Ability,
  SecondaryMission,
  SimulateRequest,
  SimulateResponse,
  TurnStateOut,
  Unit,
  UnitAttachment,
  UnitDefinition,
  UnitOut,
  UnitSynergy,
} from "./types";

// Derived from the page's own hostname (not hardcoded to "localhost") so this works
// identically whether the frontend was loaded as localhost:5173 (on this machine) or
// 192.168.x.x:5173 (from another machine on the LAN) -- the backend always lives on the
// same host, just port 8000 instead of 5173.
const BASE_URL = `http://${window.location.hostname}:8000`;

// --- Auth token (bearer) -----------------------------------------------------
// Persisted in localStorage so a reload stays logged in. Kept as a module-level value so
// request() below can attach it without every call site threading it through.
const TOKEN_KEY = "wh_token";
let authToken: string | null = localStorage.getItem(TOKEN_KEY);
// The app registers this so a 401 (expired/cleared token) can bounce the user back to login.
let onUnauthorized: (() => void) | null = null;

export function getToken(): string | null {
  return authToken;
}

export function setToken(token: string | null): void {
  authToken = token;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** Carries the HTTP status so callers can react to it (e.g. 409 vs a server/network failure).
 *  status is 0 when the request never reached the server (network error / CORS / server down). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: { ...headers, ...(options?.headers as Record<string, string> | undefined) },
    });
  } catch {
    // Never reached the server: backend down, wrong host, or CORS blocked the request.
    throw new ApiError(0, `${options?.method ?? "GET"} ${path} failed: could not reach the server`);
  }
  if (!resp.ok) {
    // A 401 means the stored token is gone/invalid -- drop it and let the app show login.
    if (resp.status === 401) {
      setToken(null);
      onUnauthorized?.();
    }
    const body = await resp.text();
    throw new ApiError(resp.status, `${options?.method ?? "GET"} ${path} failed: ${resp.status} ${body}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const api = {
  // --- Auth. register/login store the returned token; logout/me use the current one. ---
  register: async (username: string, password: string) => {
    const res = await request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(res.token);
    return res;
  },
  login: async (username: string, password: string) => {
    const res = await request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(res.token);
    return res;
  },
  logout: async () => {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
    }
  },
  me: () => request<AuthUser>("/auth/me"),

  listRosters: () => request<Roster[]>("/rosters"),
  getRoster: (id: number) => request<Roster>(`/rosters/${id}`),
  createRoster: (payload: { name: string; faction: string; points_limit?: number | null }) =>
    request<Roster>("/rosters", { method: "POST", body: JSON.stringify(payload) }),
  updateRoster: (
    id: number,
    payload: Partial<Pick<Roster, "name" | "faction" | "points_limit" | "detachments" | "disposition">>,
  ) =>
    request<Roster>(`/rosters/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteRoster: (id: number) => request<void>(`/rosters/${id}`, { method: "DELETE" }),
  importRoster: (data: unknown) =>
    request<RosterImportResult>("/rosters/import", { method: "POST", body: JSON.stringify(data) }),

  listUnits: (rosterId: number) => request<UnitOut[]>(`/rosters/${rosterId}/units`),
  addUnit: (rosterId: number, payload: { unit_definition_id: string; quantity: number }) =>
    request<UnitOut>(`/rosters/${rosterId}/units`, { method: "POST", body: JSON.stringify(payload) }),
  updateUnit: (rosterId: number, unitId: number, payload: Partial<Pick<Unit, "notes" | "quantity" | "buffs" | "model_groups">>) =>
    request<UnitOut>(`/rosters/${rosterId}/units/${unitId}`, { method: "PATCH", body: JSON.stringify(payload) }),
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
  listAllUnitDefinitions: () => request<UnitDefinition[]>("/unit-definitions"),
  listUnitDefinitionsByFaction: (faction: string) =>
    request<UnitDefinition[]>(`/unit-definitions?faction=${encodeURIComponent(faction)}`),
  listFactions: () => request<string[]>("/unit-definitions/factions"),

  simulate: (body: SimulateRequest) => request<SimulateResponse>("/simulate", { method: "POST", body: JSON.stringify(body) }),
  analyzeAbilities: (abilities: Ability[]) =>
    request<AnalyzeResponse>("/simulate/analyze", { method: "POST", body: JSON.stringify({ abilities }) }),

  listArmyRules: () => request<FactionArmyRules[]>("/army-rules"),
  listDetachments: () => request<FactionDetachments[]>("/detachments"),
  listPrimaryMissions: () => request<Mission[]>("/primary-missions"),
  listSecondaryMissions: () => request<SecondaryMission[]>("/secondary-missions"),
  listLayouts: () => request<LayoutMatchup[]>("/layouts"),

  createBattle: (payload: {
    roster_id?: number | null;
    opponent_name?: string | null;
    opponent_roster_id?: number | null;
    your_disposition?: Disposition | null;
    opponent_disposition?: Disposition | null;
    layout_number?: number | null;
  }) => request<BattleOut>("/battles", { method: "POST", body: JSON.stringify(payload) }),
  listBattlesForRoster: (rosterId: number) => request<BattleOut[]>(`/battles?roster_id=${rosterId}`),
  listBattles: () => request<BattleOut[]>("/battles"),
  getBattle: (id: number) => request<BattleOut>(`/battles/${id}`),
  deleteBattle: (id: number) => request<void>(`/battles/${id}`, { method: "DELETE" }),
  updateBattleSetup: (
    battleId: number,
    payload: Partial<{
      opponent_name: string | null;
      opponent_roster_id: number | null;
      your_disposition: Disposition | null;
      opponent_disposition: Disposition | null;
      layout_number: number | null;
    }>,
  ) => request<BattleOut>(`/battles/${battleId}/setup`, { method: "PATCH", body: JSON.stringify(payload) }),
  advancePhase: (id: number) => request<BattleOut>(`/battles/${id}/advance-phase`, { method: "PATCH" }),
  retreatPhase: (id: number) => request<BattleOut>(`/battles/${id}/retreat-phase`, { method: "PATCH" }),
  updatePlayer: (
    battleId: number,
    playerNumber: number,
    payload: Partial<Pick<PlayerState, "cp_gained" | "cp_spent" | "vp_adjustment">>,
  ) =>
    request<PlayerState>(`/battles/${battleId}/players/${playerNumber}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  adjustMissionScore: (
    battleId: number,
    playerNumber: number,
    payload: { section_index: number; tier_index: number; delta: number },
  ) =>
    request<BattleOut>(`/battles/${battleId}/players/${playerNumber}/mission-score`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  addEffect: (
    battleId: number,
    payload: { label: string; owner_player: number; duration_type: string; unit_id?: number },
  ) => request<BattleOut>(`/battles/${battleId}/effects`, { method: "POST", body: JSON.stringify(payload) }),
  dismissEffect: (battleId: number, effectId: number) =>
    request<BattleOut>(`/battles/${battleId}/effects/${effectId}`, { method: "DELETE" }),

  acknowledgeSynergy: (battleId: number, synergyId: number) =>
    request<BattleOut>(`/battles/${battleId}/synergies/${synergyId}/acknowledge`, { method: "POST" }),

  spendPool: (battleId: number, poolId: number, amount = 1, ownerPlayer = 1) =>
    request<BattleOut>(`/battles/${battleId}/pools/${poolId}/spend`, {
      method: "POST",
      body: JSON.stringify({ amount, owner_player: ownerPlayer }),
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
