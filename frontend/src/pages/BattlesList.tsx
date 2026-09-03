import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { BattleOut, Roster } from "../types";

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function BattlesList() {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listRosters().then(setRosters).catch((e) => setError(String(e)));
    api
      .listBattles()
      .then((b) => setBattles([...b].sort((a, c) => c.started_at.localeCompare(a.started_at))))
      .catch((e) => setError(String(e)));
  }, []);

  function rosterName(rosterId: number | null): string {
    return rosters.find((r) => r.id === rosterId)?.name ?? `Roster #${rosterId ?? "?"}`;
  }

  return (
    <div className="page">
      <h1>Battles</h1>
      {error && <p className="error">{error}</p>}
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
            </li>
          );
        })}
        {battles.length === 0 && <li className="muted">No battles yet.</li>}
      </ul>
    </div>
  );
}
