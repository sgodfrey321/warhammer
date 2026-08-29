import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { DURATION_TYPES, STAT_ORDER, WEAPON_STAT_ORDER } from "../types";
import type { BattleOut, DeclaredStatePool, Phase, UnitAttachment, UnitOut, Weapon } from "../types";

function statLine(stats: Record<string, string>): string {
  return STAT_ORDER.filter((k) => stats[k]).map((k) => `${k} ${stats[k]}`).join("  ");
}

function weaponLine(w: Weapon): string {
  return WEAPON_STAT_ORDER.filter((k) => w.characteristics[k])
    .map((k) => `${k} ${w.characteristics[k]}`)
    .join("  ");
}

// GW/BattleScribe ability text markup, confirmed against real indexer output: "**bold**" is
// plain markdown bold; "^^keyword^^" is GW's own convention for a keyword being referenced
// (not a real hyperlink -- there's no per-keyword rules page in this data -- but visually
// distinct all the same). They nest, e.g. "**^^Dire Avengers^^**", so this recurses into a
// bold match's own content rather than a single non-nested regex pass.
const MARKUP_RE = /\*\*(.+?)\*\*|\^\^(.+?)\^\^/;

function renderAbilityText(text: string, keyPrefix = "n"): React.ReactNode[] {
  const match = MARKUP_RE.exec(text);
  if (!match) return [text];
  const [full, bold, keyword] = match;
  const before = text.slice(0, match.index);
  const after = text.slice(match.index + full.length);
  const nodes: React.ReactNode[] = [];
  if (before) nodes.push(before);
  if (bold !== undefined) {
    nodes.push(<strong key={`${keyPrefix}-b`}>{renderAbilityText(bold, `${keyPrefix}-bi`)}</strong>);
  } else {
    nodes.push(
      <span key={`${keyPrefix}-k`} className="ability-keyword">
        {keyword}
      </span>,
    );
  }
  nodes.push(...renderAbilityText(after, `${keyPrefix}-n`));
  return nodes;
}

interface UnitGroup {
  key: number;
  units: UnitOut[];
}

// Attached units (a Character leading a bodyguard unit) act as one combined unit for
// movement/shooting/charging/fighting -- grouped here so they share one set of turn-state
// controls instead of tracking each member separately. A led unit is the group's anchor
// (its own id doubles as the group key); a leader always belongs to the unit it leads.
function groupUnits(units: UnitOut[], attachments: UnitAttachment[]): UnitGroup[] {
  const leaderToLed = new Map(attachments.map((a) => [a.leader_unit_id, a.led_unit_id]));
  const groups = new Map<number, UnitOut[]>();
  for (const u of units) {
    const key = leaderToLed.get(u.id) ?? u.id;
    const existing = groups.get(key);
    if (existing) existing.push(u);
    else groups.set(key, [u]);
  }
  return Array.from(groups, ([key, groupUnits]) => ({ key, units: groupUnits }));
}

const PHASE_CHECKLIST: Record<Phase, string[]> = {
  command: [
    "Gain Core CP (automatic, both players, every Command phase).",
    "Battle-shock: check any units at half strength or below (manual, not tracked here).",
    "Command abilities / stratagems: log any resulting effect below.",
  ],
  movement: ["Set each unit's move type below.", "Advance/Fall Back will warn if that unit later shoots or charges."],
  shooting: ["Resolve synergy reminders above before selecting targets.", "Mark units has_shot below."],
  charge: [
    "Declared choices (e.g. Scent of Blood-style bonuses) happen at declaration time, not tracked here.",
    "Mark units has_charged below.",
  ],
  fight: [
    "Sub-steps: start → pile-in → fight → consolidate → end (outer shell only).",
    "Fights-First is an informational tag, not an enforced activation order.",
    "Mark units has_fought below.",
  ],
};

export function BattleTracker() {
  const { id } = useParams();
  const battleId = Number(id);

  const [battle, setBattle] = useState<BattleOut | null>(null);
  const [units, setUnits] = useState<UnitOut[]>([]);
  const [attachments, setAttachments] = useState<UnitAttachment[]>([]);
  const [pools, setPools] = useState<DeclaredStatePool[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [label, setLabel] = useState("");
  const [ownerPlayer, setOwnerPlayer] = useState(1);
  const [durationType, setDurationType] = useState<string>(DURATION_TYPES[0]);
  const [stackingInputs, setStackingInputs] = useState<Record<number, { owner: number; value: number }>>({});
  const [expandedAbilities, setExpandedAbilities] = useState<Set<number>>(new Set());
  const [expandedWeapons, setExpandedWeapons] = useState<Set<number>>(new Set());

  function toggleAbilities(unitId: number) {
    setExpandedAbilities((prev) => {
      const next = new Set(prev);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  }

  function toggleWeapons(unitId: number) {
    setExpandedWeapons((prev) => {
      const next = new Set(prev);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  }

  function refresh() {
    api.getBattle(battleId).then((b) => {
      setBattle(b);
      if (b.roster_id) {
        api.listUnits(b.roster_id).then(setUnits).catch((e) => setError(String(e)));
        api.listAttachments(b.roster_id).then(setAttachments).catch((e) => setError(String(e)));
        api.listPools(b.roster_id).then(setPools).catch((e) => setError(String(e)));
      }
    }).catch((e) => setError(String(e)));
  }

  useEffect(refresh, [battleId]);

  async function handleAdvance() {
    try {
      setBattle(await api.advancePhase(battleId));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddEffect(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) return;
    try {
      setBattle(await api.addEffect(battleId, { label, owner_player: ownerPlayer, duration_type: durationType }));
      setLabel("");
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDismiss(effectId: number) {
    try {
      setBattle(await api.dismissEffect(battleId, effectId));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handlePlayerChange(playerNumber: number, field: "cp_gained" | "cp_spent" | "vp", value: number) {
    try {
      await api.updatePlayer(battleId, playerNumber, { [field]: value });
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAcknowledgeSynergy(synergyId: number) {
    try {
      setBattle(await api.acknowledgeSynergy(battleId, synergyId));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleSpendPool(poolId: number) {
    try {
      setBattle(await api.spendPool(battleId, poolId, 1));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddPoolEntry(poolId: number) {
    const input = stackingInputs[poolId] ?? { owner: 1, value: 1 };
    try {
      setBattle(await api.addPoolEntry(battleId, poolId, input.owner, input.value));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleTurnStateChange(unitIds: number[], field: string, value: string | boolean) {
    try {
      // Attached units share one turn state -- every member gets the same update so they
      // stay in sync, since they move/shoot/charge/fight as one combined unit.
      await Promise.all(unitIds.map((unitId) => api.updateTurnState(battleId, unitId, { [field]: value })));
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  if (!battle) return <div className="page">Loading...</div>;

  return (
    <div className="page">
      <h1>Battle #{battle.id}</h1>
      {error && <p className="error">{error}</p>}

      <div className="phase-banner">
        <div className="phase-name">{battle.current_phase.toUpperCase()} PHASE</div>
        <div className="muted">
          Battle Round {battle.battle_round} — Player {battle.active_player}'s turn (step {battle.global_step})
        </div>
        <button type="button" className="primary" onClick={handleAdvance}>
          Advance Phase →
        </button>
      </div>

      <ul className="phase-checklist">
        {PHASE_CHECKLIST[battle.current_phase].map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      {battle.active_synergies.length > 0 && (
        <div className="synergy-banner">
          <strong>Synergy reminder:</strong>
          <ul>
            {battle.active_synergies.map((s) => (
              <li key={s.id}>
                {s.note || `Trigger during ${s.trigger_phase} phase`}
                <button type="button" className="link-button" onClick={() => handleAcknowledgeSynergy(s.id)}>
                  acknowledge
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <section className="players">
        {battle.players.map((p) => (
          <div key={p.id} className="player-card">
            <h3>Player {p.player_number}</h3>
            <label>
              CP Gained
              <input
                type="number"
                value={p.cp_gained}
                onChange={(e) => handlePlayerChange(p.player_number, "cp_gained", Number(e.target.value))}
              />
            </label>
            <label>
              CP Spent
              <input
                type="number"
                value={p.cp_spent}
                onChange={(e) => handlePlayerChange(p.player_number, "cp_spent", Number(e.target.value))}
              />
            </label>
            <label>
              VP
              <input
                type="number"
                value={p.vp}
                onChange={(e) => handlePlayerChange(p.player_number, "vp", Number(e.target.value))}
              />
            </label>
          </div>
        ))}
      </section>

      {pools.length > 0 && (
        <section>
          <h2>Declared State Pools</h2>
          <ul className="pool-list">
            {pools.map((pool) => {
              if (pool.stacking) {
                const entries = battle.pool_entries.filter((e) => e.pool_id === pool.id);
                const input = stackingInputs[pool.id] ?? { owner: 1, value: 1 };
                return (
                  <li key={pool.id}>
                    <strong>{pool.name}</strong> <span className="tag">{pool.scope}, stacking</span>
                    <div className="pool-entries">
                      {entries.map((e) => (
                        <span key={e.id} className="tag">
                          P{e.owner_player}: {e.value}
                        </span>
                      ))}
                      {entries.length === 0 && <span className="muted"> none active</span>}
                    </div>
                    <div className="inline-form">
                      <select
                        value={input.owner}
                        onChange={(e) =>
                          setStackingInputs({ ...stackingInputs, [pool.id]: { ...input, owner: Number(e.target.value) } })
                        }
                      >
                        <option value={1}>Player 1</option>
                        <option value={2}>Player 2</option>
                      </select>
                      <input
                        type="number"
                        value={input.value}
                        onChange={(e) =>
                          setStackingInputs({ ...stackingInputs, [pool.id]: { ...input, value: Number(e.target.value) } })
                        }
                      />
                      <button type="button" onClick={() => handleAddPoolEntry(pool.id)}>
                        Add
                      </button>
                    </div>
                  </li>
                );
              }
              const states = battle.pool_states.filter((s) => s.pool_id === pool.id);
              return (
                <li key={pool.id}>
                  <strong>{pool.name}</strong> <span className="tag">{pool.scope}</span>
                  {[1, 2].map((owner) => {
                    const state = states.find((s) => s.owner_player === owner);
                    const value = state?.current_value ?? pool.max_value;
                    return (
                      <span key={owner} className="muted">
                        {" "}
                        P{owner}: {value}/{pool.max_value}
                      </span>
                    );
                  })}
                  <button type="button" className="link-button" onClick={() => handleSpendPool(pool.id)}>
                    spend 1 (active player)
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {units.length > 0 && (
        <section>
          <h2>Unit Turn States</h2>
          <ul className="turn-state-list">
            {groupUnits(units, attachments).map((group) => {
              const unitIds = group.units.map((u) => u.id);
              // After a sync all members' turn states match -- read the first as representative.
              const state = battle.turn_states.find((t) => t.unit_id === group.units[0].id);
              const warnings = group.units
                .map((u) => battle.turn_states.find((t) => t.unit_id === u.id)?.eligibility_warning)
                .filter((w): w is string => !!w);
              const grouped = group.units.length > 1;
              return (
                <li key={group.key} className={grouped ? "unit-group" : undefined}>
                  {grouped && <div className="unit-group-label">Attached unit</div>}
                  {group.units.map((u) => {
                    const stats = u.unit_definition.stats;
                    const abilities = u.unit_definition.abilities;
                    const loadout = u.loadout;
                    const line = statLine(stats);
                    return (
                      <div key={u.id}>
                        <div className="unit-header">
                          <strong>{u.unit_definition.name}</strong>
                          {line ? (
                            <span className="stat-line">{line}</span>
                          ) : (
                            <span className="muted"> stats not indexed yet</span>
                          )}
                          {abilities.length > 0 && (
                            <button type="button" className="link-button" onClick={() => toggleAbilities(u.id)}>
                              {expandedAbilities.has(u.id) ? "hide abilities" : `abilities (${abilities.length})`}
                            </button>
                          )}
                          {loadout.length > 0 && (
                            <button type="button" className="link-button" onClick={() => toggleWeapons(u.id)}>
                              {expandedWeapons.has(u.id) ? "hide weapons" : `weapons (${loadout.length})`}
                            </button>
                          )}
                        </div>
                        {expandedAbilities.has(u.id) && (
                          <ul className="ability-list">
                            {abilities.map((a) => (
                              <li key={a.name}>
                                <strong>{a.name}:</strong> {renderAbilityText(a.text, a.name)}
                              </li>
                            ))}
                          </ul>
                        )}
                        {expandedWeapons.has(u.id) && (
                          <ul className="ability-list">
                            {loadout.map((item) => {
                              const weapon = u.unit_definition.weapons.find((w) => w.name === item.name);
                              return (
                                <li key={item.name}>
                                  <strong>
                                    {item.count}x {item.name}
                                  </strong>
                                  {weapon ? (
                                    <span className="stat-line"> {weaponLine(weapon)}</span>
                                  ) : (
                                    <span className="muted"> profile not indexed</span>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                  <select
                    value={state?.move_type ?? ""}
                    onChange={(e) => handleTurnStateChange(unitIds, "move_type", e.target.value)}
                  >
                    <option value="">move type...</option>
                    <option value="stationary">stationary</option>
                    <option value="normal">normal</option>
                    <option value="advance">advance</option>
                    <option value="fall_back">fall back</option>
                    <option value="disembark">disembark</option>
                    <option value="ingress">ingress</option>
                  </select>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={state?.has_shot ?? false}
                      onChange={(e) => handleTurnStateChange(unitIds, "has_shot", e.target.checked)}
                    />
                    shot
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={state?.has_charged ?? false}
                      onChange={(e) => handleTurnStateChange(unitIds, "has_charged", e.target.checked)}
                    />
                    charged
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={state?.has_fought ?? false}
                      onChange={(e) => handleTurnStateChange(unitIds, "has_fought", e.target.checked)}
                    />
                    fought
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={state?.is_fights_first ?? false}
                      onChange={(e) => handleTurnStateChange(unitIds, "is_fights_first", e.target.checked)}
                    />
                    fights first
                  </label>
                  {warnings.map((w) => (
                    <div key={w} className="warning">
                      {w}
                    </div>
                  ))}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section>
        <h2>Active Effects</h2>
        <form className="inline-form" onSubmit={handleAddEffect}>
          <input
            type="text"
            placeholder="Effect label (e.g. Doom)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            required
          />
          <select value={ownerPlayer} onChange={(e) => setOwnerPlayer(Number(e.target.value))}>
            <option value={1}>Player 1</option>
            <option value={2}>Player 2</option>
          </select>
          <select value={durationType} onChange={(e) => setDurationType(e.target.value)}>
            {DURATION_TYPES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <button type="submit">Log Effect</button>
        </form>
        <ul className="effect-list">
          {battle.effects.map((eff) => (
            <li key={eff.id} className={eff.expired ? "expired" : ""}>
              <span className="effect-label">{eff.label}</span>
              <span className="muted"> (Player {eff.owner_player}, {eff.duration_type})</span>
              {eff.expired && <span className="tag expired-tag">expired</span>}
              <button type="button" className="link-button" onClick={() => handleDismiss(eff.id)}>
                dismiss
              </button>
            </li>
          ))}
          {battle.effects.length === 0 && <li className="muted">No active effects.</li>}
        </ul>
      </section>
    </div>
  );
}
