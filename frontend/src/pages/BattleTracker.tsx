import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { matchFaction } from "../catalog";
import { capitalize } from "../format";
import { renderAbilityText } from "../markup";
import { findMission } from "../missions";
import { DURATION_TYPES, PHASES, STAT_ORDER, WEAPON_STAT_ORDER } from "../types";
import type {
  BattleOut,
  DeclaredStatePool,
  FactionArmyRules,
  Mission,
  Phase,
  Roster,
  UnitAttachment,
  UnitBuff,
  UnitOut,
  Weapon,
} from "../types";
import { auraAbilityReferences, groupUnitsByRole, leaderAbilityReferences, psychicAbilityReferences } from "../units";
import { groupLoadoutByRangeType, matchLoadoutWeapons, weaponBaseName } from "../weapons";

// A unit's stats rendered token-by-token (not one joined string) so a declared buff (see
// RosterEditor's "Unit Buffs") can be pinned as a badge right next to the one characteristic
// it applies to -- a preview of what spending a token (Battle Focus, etc.) could buy, shown
// before anything is actually spent.
function renderStatLine(stats: Record<string, string>, buffs: UnitBuff[]): React.ReactNode | null {
  const keys = STAT_ORDER.filter((k) => stats[k]);
  if (keys.length === 0) return null;
  return (
    <span className="stat-line">
      {keys.map((k, i) => {
        const buff = buffs.find((b) => b.stat === k);
        return (
          <span key={k}>
            {i > 0 && "  "}
            {k} {stats[k]}
            {buff && (
              <span className="buff-badge" title={buff.label}>
                {buff.modifier}
              </span>
            )}
          </span>
        );
      })}
    </span>
  );
}

function weaponLine(w: Weapon): string {
  return WEAPON_STAT_ORDER.filter((k) => w.characteristics[k])
    .map((k) => `${k} ${w.characteristics[k]}`)
    .join("  ");
}

interface UnitGroup {
  key: number;
  units: UnitOut[];
}

// Attached units (a Character leading a bodyguard unit) act as one combined unit for
// movement/shooting/charging/fighting -- combined here so they share one set of turn-state
// controls instead of tracking each member separately. Leaders first, led unit last -- mirrors
// RosterEditor's card ordering (and its role-group placement: a leader always renders under
// whichever role group its led unit belongs to, never its own natural role).
function combinedGroup(ledUnit: UnitOut, units: UnitOut[], attachments: UnitAttachment[]): UnitGroup {
  const leaders = attachments
    .filter((a) => a.led_unit_id === ledUnit.id)
    .map((a) => units.find((u) => u.id === a.leader_unit_id))
    .filter((u): u is UnitOut => !!u);
  return { key: ledUnit.id, units: [...leaders, ledUnit] };
}

// Mirrors backend/app/phases.py's pure functions so the nav buttons can name their
// destination without a round-trip -- global_step is the only source of truth, these
// just read it the same way the server does.
function phaseAtStep(step: number): Phase {
  return PHASES[((step % PHASES.length) + PHASES.length) % PHASES.length];
}
function activePlayerAtStep(step: number): number {
  return Math.floor(step / PHASES.length) % 2 === 0 ? 1 : 2;
}

// Keeps keystrokes local and only PATCHes on blur/Enter, so typing "12" doesn't fire two requests.
function CommitNumberInput({ value, title, onCommit }: { value: number; title?: string; onCommit: (n: number) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  function commit() {
    if (draft === null) return;
    const n = Number(draft);
    setDraft(null);
    if (draft.trim() !== "" && Number.isFinite(n) && n !== value) onCommit(n);
  }
  return (
    <input
      type="number"
      title={title}
      value={draft ?? value}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
    />
  );
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
  const [roster, setRoster] = useState<Roster | null>(null);
  const [units, setUnits] = useState<UnitOut[]>([]);
  const [attachments, setAttachments] = useState<UnitAttachment[]>([]);
  const [opponentUnits, setOpponentUnits] = useState<UnitOut[]>([]);
  const [opponentAttachments, setOpponentAttachments] = useState<UnitAttachment[]>([]);
  const [opponentRoster, setOpponentRoster] = useState<Roster | null>(null);
  const [pools, setPools] = useState<DeclaredStatePool[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [armyRules, setArmyRules] = useState<FactionArmyRules[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"meta" | "rules" | "units">("meta");

  const [label, setLabel] = useState("");
  const [ownerPlayer, setOwnerPlayer] = useState(1);
  const [durationType, setDurationType] = useState<string>(DURATION_TYPES[0]);
  const [effectUnitId, setEffectUnitId] = useState<number | "">("");
  const [stackingInputs, setStackingInputs] = useState<Record<number, { owner: number; value: number }>>({});
  const [expandedDetails, setExpandedDetails] = useState<Set<number>>(new Set());

  function unitName(unitId: number): string {
    return units.find((u) => u.id === unitId)?.unit_definition.name ?? `#${unitId}`;
  }

  function toggleDetails(unitId: number) {
    setExpandedDetails((prev) => {
      const next = new Set(prev);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  }

  // Full load (battle + both rosters' units/attachments/pools) -- only on mount/battleId change.
  function loadAll() {
    api.getBattle(battleId).then((b) => {
      setBattle(b);
      if (b.roster_id) {
        api.getRoster(b.roster_id).then(setRoster).catch((e) => setError(String(e)));
        api.listUnits(b.roster_id).then(setUnits).catch((e) => setError(String(e)));
        api.listAttachments(b.roster_id).then(setAttachments).catch((e) => setError(String(e)));
        api.listPools(b.roster_id).then(setPools).catch((e) => setError(String(e)));
      }
      if (b.opponent_roster_id) {
        api.getRoster(b.opponent_roster_id).then(setOpponentRoster).catch((e) => setError(String(e)));
        api.listUnits(b.opponent_roster_id).then(setOpponentUnits).catch((e) => setError(String(e)));
        api.listAttachments(b.opponent_roster_id).then(setOpponentAttachments).catch((e) => setError(String(e)));
      } else {
        setOpponentUnits([]);
        setOpponentAttachments([]);
        setOpponentRoster(null);
      }
    }).catch((e) => setError(String(e)));
  }

  // After a mutation only the battle's own state can have changed.
  function refreshBattle() {
    api.getBattle(battleId).then(setBattle).catch((e) => setError(String(e)));
  }

  useEffect(loadAll, [battleId]);

  useEffect(() => {
    api.listArmyRules().then(setArmyRules).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    api.listPrimaryMissions().then(setMissions).catch((e) => setError(String(e)));
  }, []);

  async function handleAdvance() {
    try {
      setBattle(await api.advancePhase(battleId));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleRetreat() {
    try {
      setBattle(await api.retreatPhase(battleId));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddEffect(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) return;
    try {
      setBattle(
        await api.addEffect(battleId, {
          label,
          owner_player: ownerPlayer,
          duration_type: durationType,
          unit_id: effectUnitId === "" ? undefined : effectUnitId,
        }),
      );
      setLabel("");
      setEffectUnitId("");
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

  // One-click version of "Log Effect" for a Psychic Power Reference entry -- owner_player is
  // always 1 (the tracked roster's own player, matching missionForPlayer's convention below),
  // and duration_type defaults to "until_next_command_phase" since that's the wording nearly
  // every psychic power in the indexed data actually uses ("until the start of your next
  // Command phase"). Still just a starting point in the same Active Effects list -- edit or
  // dismiss it there like any manually-logged effect if a given power reads differently.
  async function handleLogAbility(unit: UnitOut, abilityName: string) {
    try {
      setBattle(
        await api.addEffect(battleId, {
          label: `${abilityName} — ${unit.unit_definition.name}`,
          owner_player: 1,
          duration_type: "until_next_command_phase",
          unit_id: unit.id,
        }),
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function handlePlayerChange(
    playerNumber: number,
    field: "cp_gained" | "cp_spent" | "vp_adjustment",
    value: number,
  ) {
    try {
      await api.updatePlayer(battleId, playerNumber, { [field]: value });
      refreshBattle();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAdjustMissionScore(playerNumber: number, sectionIndex: number, tierIndex: number, delta: number) {
    try {
      setBattle(
        await api.adjustMissionScore(battleId, playerNumber, {
          section_index: sectionIndex,
          tier_index: tierIndex,
          delta,
        }),
      );
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
      setBattle(await api.spendPool(battleId, poolId, 1, 1));
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
      const updated = await Promise.all(unitIds.map((unitId) => api.updateTurnState(battleId, unitId, { [field]: value })));
      setBattle((b) => {
        if (!b) return b;
        const byUnit = new Map(updated.map((t) => [t.unit_id, t]));
        const known = new Set(b.turn_states.map((t) => t.unit_id));
        return {
          ...b,
          turn_states: [...b.turn_states.map((t) => byUnit.get(t.unit_id) ?? t), ...updated.filter((t) => !known.has(t.unit_id))],
        };
      });
    } catch (e) {
      setError(String(e));
    }
  }

  if (!battle) return <div className="page">Loading...</div>;

  // Each army whose turn states are rendered: your roster, plus the opponent roster if one is linked.
  const armies = [
    { key: "you", heading: opponentUnits.length > 0 ? "Your army" : "Unit Turn States", units, attachments },
    ...(opponentUnits.length > 0
      ? [{ key: "opp", heading: `Opponent — ${opponentRoster?.name ?? "army"}`, units: opponentUnits, attachments: opponentAttachments }]
      : []),
  ];
  const leaderReferences = leaderAbilityReferences(units);
  const auraReferences = auraAbilityReferences(units);
  const psychicReferences = psychicAbilityReferences(units);
  const factionRules = roster ? matchFaction(armyRules, roster.faction) : undefined;

  const nextStep = battle.global_step + 1;
  const prevStep = battle.global_step - 1;
  const nextPhase = phaseAtStep(nextStep);
  const nextPlayer = activePlayerAtStep(nextStep);
  const prevPhase = prevStep >= 0 ? phaseAtStep(prevStep) : null;
  const prevPlayer = prevStep >= 0 ? activePlayerAtStep(prevStep) : null;

  const hasMissionSetup = Boolean(battle.your_disposition && battle.opponent_disposition);

  // Player 1 is "you" (the tracked roster's owner -- your_disposition is their disposition),
  // player 2 is the opponent -- mirrors the asymmetric deck/vs lookup used on /missions and the
  // setup screen.
  function missionForPlayer(playerNumber: number): Mission | undefined {
    if (!hasMissionSetup) return undefined;
    const deck = playerNumber === 1 ? battle!.your_disposition : battle!.opponent_disposition;
    const vs = playerNumber === 1 ? battle!.opponent_disposition : battle!.your_disposition;
    return findMission(missions, deck, vs);
  }

  function achievedCount(playerNumber: number, sectionIndex: number, tierIndex: number): number {
    return (
      battle!.mission_scores.find(
        (s) => s.player_number === playerNumber && s.section_index === sectionIndex && s.tier_index === tierIndex,
      )?.achieved_count ?? 0
    );
  }

  return (
    <div className="page battle-page">
      <h1>Battle #{battle.id}</h1>
      {error && <p className="error">{error}</p>}

      <div className={`phase-banner phase-${battle.current_phase}`}>
        <div className="phase-banner-main">
          <div>
            <div className="phase-name">{battle.current_phase.toUpperCase()} PHASE</div>
            <div className="muted">
              Battle Round {battle.battle_round} — step {battle.global_step}
            </div>
          </div>
          <div className="phase-nav">
            <button type="button" onClick={handleRetreat} disabled={prevStep < 0}>
              {prevPhase
                ? `← ${capitalize(prevPhase)}${prevPlayer !== battle.active_player ? ` (P${prevPlayer})` : ""}`
                : "← Previous Phase"}
            </button>
            <button type="button" className="primary" onClick={handleAdvance}>
              {capitalize(nextPhase)}
              {nextPlayer !== battle.active_player ? ` (P${nextPlayer})` : ""} →
            </button>
          </div>
        </div>
        <div className="muted small">
          Going back only moves the phase pointer — CP already granted and resource pools already
          refilled/cleared crossing that boundary aren't undone.
        </div>
      </div>

      <div className="tab-bar battle-tabs">
        <button type="button" className={activeTab === "meta" ? "active" : ""} onClick={() => setActiveTab("meta")}>
          Meta
        </button>
        <button type="button" className={activeTab === "rules" ? "active" : ""} onClick={() => setActiveTab("rules")}>
          Rules
        </button>
        <button type="button" className={activeTab === "units" ? "active" : ""} onClick={() => setActiveTab("units")}>
          Units
        </button>
      </div>

      <div className="battle-columns">
        <div className={`battle-meta battle-tab-panel${activeTab !== "meta" ? " mobile-hidden" : ""}`}>
          <ul className="phase-checklist">
            {PHASE_CHECKLIST[battle.current_phase].map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <div className="players-stack">
            {[2, 1].map((playerNumber) => {
              const p = battle.players.find((pl) => pl.player_number === playerNumber);
              if (!p) return null;
              const label = playerNumber === 1 ? "You" : battle.opponent_name || "Opponent";
              const mission = missionForPlayer(playerNumber);
              return (
                <div
                  key={playerNumber}
                  className={`player-panel${playerNumber === battle.active_player ? " active" : ""}`}
                >
                  <h2>{label}</h2>
                  <div className="cp-block">
                    <span className="player-field">
                      CP
                      <CommitNumberInput
                        title="CP Gained"
                        value={p.cp_gained}
                        onCommit={(n) => handlePlayerChange(playerNumber, "cp_gained", n)}
                      />
                      /
                      <CommitNumberInput
                        title="CP Spent"
                        value={p.cp_spent}
                        onCommit={(n) => handlePlayerChange(playerNumber, "cp_spent", n)}
                      />
                    </span>
                    <span className="cp-total">{p.cp_gained - p.cp_spent} CP</span>
                  </div>

                  {mission ? (
                    <details className="primary-block role-group" open>
                      <summary className="role-group-header">
                        <span>
                          Primary — {mission.name} ({p.vp - p.vp_adjustment} VP)
                        </span>
                      </summary>
                      {mission.sections.map((section, si) =>
                        section.tiers.map((tier, ti) => {
                          const count = achievedCount(playerNumber, si, ti);
                          return (
                            <div key={`${si}-${ti}`} className="tier-row">
                              <div className="tier-row-text">
                                <div>{renderAbilityText(tier.text, `${playerNumber}-${si}-${ti}`)}</div>
                                <div className="muted small">
                                  {tier.vp} VP | {section.when}
                                  {section.trigger && ` — ${section.trigger}`}
                                </div>
                              </div>
                              <div className="tier-stepper">
                                <button
                                  type="button"
                                  onClick={() => handleAdjustMissionScore(playerNumber, si, ti, -1)}
                                >
                                  −
                                </button>
                                <span>{count}</span>
                                <button
                                  type="button"
                                  onClick={() => handleAdjustMissionScore(playerNumber, si, ti, 1)}
                                >
                                  +
                                </button>
                              </div>
                            </div>
                          );
                        }),
                      )}
                      {mission.rule && (
                        <div className="mission-reverse">
                          <div className="mission-section-header">Reverse</div>
                          <p>{renderAbilityText(mission.rule, `${playerNumber}-reverse`)}</p>
                        </div>
                      )}
                      <label className="vp-adjustment">
                        VP adjustment
                        <CommitNumberInput
                          value={p.vp_adjustment}
                          onCommit={(n) => handlePlayerChange(playerNumber, "vp_adjustment", n)}
                        />
                      </label>
                      <div className="vp-total">Total VP: {p.vp}</div>
                    </details>
                  ) : (
                    <p className="muted">No mission set up.</p>
                  )}
                </div>
              );
            })}
          </div>

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

          {pools.length > 0 && (
            <details className="accordion" open>
              <summary>Declared State Pools</summary>
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
                              setStackingInputs({
                                ...stackingInputs,
                                [pool.id]: { ...input, owner: Number(e.target.value) },
                              })
                            }
                          >
                            <option value={1}>Player 1</option>
                            <option value={2}>Player 2</option>
                          </select>
                          <input
                            type="number"
                            value={input.value}
                            onChange={(e) =>
                              setStackingInputs({
                                ...stackingInputs,
                                [pool.id]: { ...input, value: Number(e.target.value) },
                              })
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
                        const isActive = owner === battle.active_player;
                        return (
                          <div key={owner} className="pool-tally-row">
                            <span className="muted">P{owner}</span>
                            <span className="pool-tally">
                              {Array.from({ length: pool.max_value }, (_, i) => {
                                const filled = i < value;
                                return (
                                  <button
                                    type="button"
                                    key={i}
                                    className={`pool-pip ${filled ? "filled" : "empty"}`}
                                    disabled={!isActive || !filled}
                                    onClick={() => handleSpendPool(pool.id)}
                                    title={
                                      !filled
                                        ? "Already spent"
                                        : isActive
                                          ? "Click to spend one"
                                          : "Only the active player can spend"
                                    }
                                  >
                                    ●
                                  </button>
                                );
                              })}
                            </span>
                            <span className="muted">
                              {value}/{pool.max_value}
                            </span>
                          </div>
                        );
                      })}
                    </li>
                  );
                })}
              </ul>
            </details>
          )}

          <details className="accordion effects-section" open>
            <summary>Active Effects</summary>
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
              <select
                value={effectUnitId}
                onChange={(e) => setEffectUnitId(e.target.value === "" ? "" : Number(e.target.value))}
              >
                <option value="">Unit (optional)...</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.unit_definition.name}
                  </option>
                ))}
              </select>
              <button type="submit">Log Effect</button>
            </form>
            <ul className="effect-list">
              {battle.effects.map((eff) => (
                <li key={eff.id} className={eff.expired ? "expired" : ""}>
                  <span className="effect-label">{eff.label}</span>
                  <span className="muted">
                    {" "}
                    (Player {eff.owner_player}, {eff.duration_type}
                    {eff.unit_id !== null && `, ${unitName(eff.unit_id)}`})
                  </span>
                  {eff.expired && <span className="tag expired-tag">expired</span>}
                  <button type="button" className="link-button" onClick={() => handleDismiss(eff.id)}>
                    dismiss
                  </button>
                </li>
              ))}
              {battle.effects.length === 0 && <li className="muted">No active effects.</li>}
            </ul>
          </details>
        </div>

        <div className="battle-units">
          <div className={`battle-tab-panel${activeTab !== "rules" ? " mobile-hidden" : ""}`}>
            {factionRules && (
              <details className="accordion" open>
                <summary>Army Rules — {factionRules.faction}</summary>
                <ul className="ability-list">
                  {factionRules.rules.map((r) => (
                    <li key={r.name}>
                      <strong>{r.name}:</strong> {renderAbilityText(r.text, r.name)}
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {(leaderReferences.length > 0 || auraReferences.length > 0 || psychicReferences.length > 0) && (
              <details className="accordion" open>
                <summary>Ability Reminders</summary>

                {psychicReferences.length > 0 && (
                  <details className="role-group" open>
                    <summary className="role-group-header">
                      <span>Psychic Powers</span>
                    </summary>
                    <p className="muted small">
                      Usually picked live each turn against an enemy unit. "Log" drops it into
                      Active Effects (Meta tab) below (until your next Command phase by default)
                      so it isn't forgotten by the time Shooting rolls around.
                    </p>
                    <ul className="ability-list">
                      {psychicReferences.map(({ unit, abilities }) =>
                        abilities.map((a, i) => (
                          <li key={`psy-${unit.id}-${i}`}>
                            <strong>{unit.unit_definition.name}</strong> — <strong>{a.name}</strong>:{" "}
                            {renderAbilityText(a.text, `psy-${unit.id}-${i}`)}{" "}
                            <button type="button" className="link-button" onClick={() => handleLogAbility(unit, a.name)}>
                              log
                            </button>
                          </li>
                        )),
                      )}
                    </ul>
                  </details>
                )}

                {auraReferences.length > 0 && (
                  <details className="role-group" open>
                    <summary className="role-group-header">
                      <span>Auras</span>
                    </summary>
                    <p className="muted small">Passive while this model's on the table -- nothing to log, just a reminder.</p>
                    <ul className="ability-list">
                      {auraReferences.map(({ unit, abilities }) =>
                        abilities.map((a, i) => (
                          <li key={`aura-${unit.id}-${i}`}>
                            <strong>{unit.unit_definition.name}</strong> — <strong>{a.name}</strong>:{" "}
                            {renderAbilityText(a.text, `aura-${unit.id}-${i}`)}
                          </li>
                        )),
                      )}
                    </ul>
                  </details>
                )}

                {leaderReferences.length > 0 && (
                  <details className="role-group">
                    <summary className="role-group-header">
                      <span>Leader Buffs</span>
                    </summary>
                    <p className="muted small">Applies to whatever unit each Leader is currently attached to.</p>
                    <ul className="ability-list">
                      {leaderReferences.map(({ unit, abilities }) =>
                        abilities.map((a, i) => (
                          <li key={`lead-${unit.id}-${i}`}>
                            <strong>{unit.unit_definition.name}</strong> — <strong>{a.name}</strong>:{" "}
                            {renderAbilityText(a.text, `lead-${unit.id}-${i}`)}
                          </li>
                        )),
                      )}
                    </ul>
                  </details>
                )}
              </details>
            )}
          </div>

          <div className={`battle-tab-panel${activeTab !== "units" ? " mobile-hidden" : ""}`}>
          {armies.map((army) => {
            // Alias to the army being rendered so the block below (your army + opponent) is shared.
            const units = army.units;
            const attachments = army.attachments;
            const nestedLeaderIds = new Set(attachments.map((a) => a.leader_unit_id));
            if (units.length === 0) return null;
            return (
            <section key={army.key}>
              <h2>{army.heading}</h2>
              {groupUnitsByRole(units, attachments).map((roleGroup) => (
                <details key={roleGroup.role} className="role-group" open>
                  <summary className="role-group-header">
                    <span>{roleGroup.role}</span>
                  </summary>
                  <ul className="turn-state-list">
                    {roleGroup.units
                      .filter((u) => !nestedLeaderIds.has(u.id))
                      .map((ledUnit) => {
                        const group = combinedGroup(ledUnit, units, attachments);
                        const unitIds = group.units.map((u) => u.id);
              // After a sync all members' turn states match -- read the first as representative.
              const state = battle.turn_states.find((t) => t.unit_id === group.units[0].id);
              const warnings = group.units
                .map((u) => battle.turn_states.find((t) => t.unit_id === u.id)?.eligibility_warning)
                .filter((w): w is string => !!w);
              const grouped = group.units.length > 1;
              const groupLabel = group.units.map((u) => u.unit_definition.name).join(" + ");
              return (
                <li key={group.key} className={grouped ? "unit-group" : undefined}>
                <details className="role-group">
                  <summary className="role-group-header">
                    <span>{grouped ? `Attached: ${groupLabel}` : groupLabel}</span>
                  </summary>
                  {group.units.map((u) => {
                    const stats = u.unit_definition.stats;
                    const abilities = u.unit_definition.abilities;
                    const loadout = u.loadout;
                    // Manually-added units (not from a BattleScribe import) never get a
                    // chosen loadout -- fall back to the catalogue's full weapon list (no
                    // counts, since we don't know what's actually equipped) rather than
                    // showing nothing just because there's no confirmed loadout to join
                    // against. Grouped by base name so a multi-mode weapon (strike/sweep)
                    // still shows as one entry with both profiles, same as the loadout case.
                    const hasLoadout = loadout.length > 0;
                    const catalogueGroups = hasLoadout
                      ? []
                      : Array.from(
                          u.unit_definition.weapons.reduce((map, w) => {
                            const base = weaponBaseName(w.name);
                            const arr = map.get(base) ?? [];
                            arr.push(w);
                            map.set(base, arr);
                            return map;
                          }, new Map<string, Weapon[]>()),
                        );
                    // Split by Ranged/Melee same as the loadout case -- every profile behind
                    // one base-name group shares a range_type (strike/sweep are both the same
                    // weapon's modes), so the group's first profile decides its section.
                    const catalogueGroupsByRangeType = ["Ranged Weapons", "Melee Weapons"]
                      .map((rangeType): [string, [string, Weapon[]][]] => [
                        rangeType,
                        catalogueGroups.filter(([, profiles]) => profiles[0]?.range_type === rangeType),
                      ])
                      .filter(([, groups]) => groups.length > 0);
                    const weaponsCount = hasLoadout ? loadout.length : catalogueGroups.length;
                    const line = renderStatLine(stats, u.buffs);
                    return (
                      <div key={u.id}>
                        <div className="unit-header">
                          <strong>{u.unit_definition.name}</strong>
                          {line ?? <span className="muted"> stats not indexed yet</span>}
                          {(abilities.length > 0 || weaponsCount > 0) && (
                            <button type="button" className="link-button" onClick={() => toggleDetails(u.id)}>
                              {expandedDetails.has(u.id) ? "hide details" : "details"}
                            </button>
                          )}
                        </div>
                        {u.unit_definition.rules.length > 0 && (
                          <div className="rule-tags">
                            {u.unit_definition.rules.map((r) => (
                              <span key={r} className="tag">
                                {r}
                              </span>
                            ))}
                          </div>
                        )}
                        {expandedDetails.has(u.id) && (
                          <ul className="ability-list">
                            {abilities.map((a) => (
                              <li key={a.name}>
                                <strong>{a.name}:</strong> {renderAbilityText(a.text, a.name)}
                              </li>
                            ))}
                          </ul>
                        )}
                        {expandedDetails.has(u.id) &&
                          hasLoadout &&
                          groupLoadoutByRangeType(loadout, u.unit_definition.weapons).map(([rangeType, items]) => (
                            <div key={rangeType}>
                              <h4 className="weapon-section-heading">{rangeType}</h4>
                              <ul className="ability-list">
                                {items.map((item) => {
                                  // A weapon with multiple firing modes (strike/sweep etc.) has
                                  // more than one catalogue profile for one loadout item -- show
                                  // every matching mode, not just the first.
                                  const matches = matchLoadoutWeapons(item.name, u.unit_definition.weapons);
                                  return (
                                    <li key={item.name}>
                                      <strong>
                                        {item.count}x {item.name}
                                      </strong>
                                      {matches.length === 0 && <span className="muted"> profile not indexed</span>}
                                      {matches.map((w) => (
                                        <div key={w.name} className="stat-line">
                                          {matches.length > 1 ? `${w.name.replace(/^➤\s*/, "")}: ` : ""}
                                          {weaponLine(w)}
                                        </div>
                                      ))}
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          ))}
                        {expandedDetails.has(u.id) && !hasLoadout && (
                          <ul className="ability-list">
                            <li className="muted">No chosen loadout on this roster — showing catalogue options.</li>
                          </ul>
                        )}
                        {expandedDetails.has(u.id) &&
                          !hasLoadout &&
                          catalogueGroupsByRangeType.map(([rangeType, groups]) => (
                            <div key={rangeType}>
                              <h4 className="weapon-section-heading">{rangeType}</h4>
                              <ul className="ability-list">
                                {groups.map(([base, profiles]) => (
                                  <li key={base}>
                                    <strong>{base}</strong>
                                    {profiles.map((w) => (
                                      <div key={w.name} className="stat-line">
                                        {profiles.length > 1 ? `${w.name.replace(/^➤\s*/, "")}: ` : ""}
                                        {weaponLine(w)}
                                      </div>
                                    ))}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        {battle.effects.some((eff) => eff.unit_id === u.id) && (
                          <ul className="effect-list unit-effects">
                            {battle.effects
                              .filter((eff) => eff.unit_id === u.id)
                              .map((eff) => (
                                <li key={eff.id} className={eff.expired ? "expired" : ""}>
                                  <span className="effect-label">{eff.label}</span>
                                  <span className="muted"> ({eff.duration_type})</span>
                                  {eff.expired && <span className="tag expired-tag">expired</span>}
                                  <button type="button" className="link-button" onClick={() => handleDismiss(eff.id)}>
                                    dismiss
                                  </button>
                                </li>
                              ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                  {battle.current_phase === "movement" && (
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
                  )}
                  {battle.current_phase === "shooting" && (
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={state?.has_shot ?? false}
                        onChange={(e) => handleTurnStateChange(unitIds, "has_shot", e.target.checked)}
                      />
                      shot
                    </label>
                  )}
                  {battle.current_phase === "charge" && (
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={state?.has_charged ?? false}
                        onChange={(e) => handleTurnStateChange(unitIds, "has_charged", e.target.checked)}
                      />
                      charged
                    </label>
                  )}
                  {battle.current_phase === "fight" && (
                    <>
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
                    </>
                  )}
                  {warnings.map((w) => (
                    <div key={w} className="warning">
                      {w}
                    </div>
                  ))}
                </details>
                </li>
                        );
                      })}
                  </ul>
                </details>
              ))}
            </section>
            );
          })}
          </div>
        </div>
      </div>
    </div>
  );
}
