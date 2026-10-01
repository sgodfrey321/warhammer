import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { BattleOut, Roster } from "../types";

export function Home() {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listRosters().then(setRosters).catch((e) => setError(String(e)));
    api.listBattles().then(setBattles).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="page">
      <h1>Warhammer Manager</h1>
      <p className="muted">
        Roster building, army reference, and battle tracking for Warhammer 40,000 -- pick a tab
        above to get started.
      </p>
      {error && <p className="error">{error}</p>}
      <ul className="roster-list">
        <li>
          <strong>{rosters.length}</strong> roster{rosters.length === 1 ? "" : "s"}{" "}
          <Link to="/rosters">view</Link>
        </li>
        <li>
          <strong>{battles.length}</strong> battle{battles.length === 1 ? "" : "s"}{" "}
          <Link to="/battles">view</Link>
        </li>
      </ul>
    </div>
  );
}
