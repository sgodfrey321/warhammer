import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { DURATION_TYPES } from "../types";
import type { BattleOut } from "../types";

export function BattleTracker() {
  const { id } = useParams();
  const battleId = Number(id);

  const [battle, setBattle] = useState<BattleOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [label, setLabel] = useState("");
  const [ownerPlayer, setOwnerPlayer] = useState(1);
  const [durationType, setDurationType] = useState<string>(DURATION_TYPES[0]);

  function refresh() {
    api.getBattle(battleId).then(setBattle).catch((e) => setError(String(e)));
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

      {battle.active_synergies.length > 0 && (
        <div className="synergy-banner">
          <strong>Synergy reminder:</strong>
          <ul>
            {battle.active_synergies.map((s) => (
              <li key={s.id}>
                {s.note || `Trigger during ${s.trigger_phase} phase`}
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
