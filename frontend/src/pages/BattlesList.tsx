import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { capitalize } from "../format";
import type { BattleOut, Roster } from "../types";

export function BattlesList() {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.listRosters().then(setRosters).catch((e) => setError(String(e)));
    api
      .listBattles()
      .then((b) => setBattles([...b].sort((a, c) => c.started_at.localeCompare(a.started_at))))
      .catch((e) => setError(String(e)));
  }, []);

  async function handleDelete(id: number) {
    try {
      await api.deleteBattle(id);
      setBattles((prev) => prev.filter((b) => b.id !== id));
      setConfirmingDeleteId(null);
    } catch (e) {
      setError(String(e));
    }
  }

  function rosterName(rosterId: number | null): string {
    return rosters.find((r) => r.id === rosterId)?.name ?? `Roster #${rosterId ?? "?"}`;
  }

  return (
    <div className="page">
      <h1>Battles</h1>
      {error && <p className="error">{error}</p>}
      <div className="inline-form">
        <button type="button" className="primary" onClick={() => navigate("/battles/setup")}>
          + New battle
        </button>
      </div>
      <ul className="roster-list">
        {battles.map((b) => {
          const you = b.players.find((p) => p.player_number === 1)?.vp ?? 0;
          const opp = b.players.find((p) => p.player_number === 2)?.vp ?? 0;
          return (
            <li key={b.id}>
              <Link to={`/battles/${b.id}`}>{rosterName(b.roster_id)}</Link>
              <span className="muted">
                {" "}
                vs {b.opponent_name || "Opponent"} — Round {b.battle_round}, {capitalize(b.current_phase)} phase — You{" "}
                {you} - {opp} Opponent
              </span>
              {confirmingDeleteId === b.id ? (
                <span className="delete-confirm-inline">
                  {" "}
                  Delete this battle? This can't be undone.{" "}
                  <button type="button" className="link-button" onClick={() => handleDelete(b.id)}>
                    Confirm
                  </button>
                  <button type="button" className="link-button" onClick={() => setConfirmingDeleteId(null)}>
                    Cancel
                  </button>
                </span>
              ) : (
                <button type="button" className="link-button" onClick={() => setConfirmingDeleteId(b.id)}>
                  delete
                </button>
              )}
            </li>
          );
        })}
        {battles.length === 0 && <li className="muted">No battles yet.</li>}
      </ul>
    </div>
  );
}
