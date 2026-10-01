import { useEffect, useState } from "react";
import { api } from "../api";
import { DISPOSITIONS, DISPOSITION_LABELS } from "../types";
import type { Disposition, LayoutMatchup, Mission } from "../types";
import { LayoutCarousel } from "./LayoutCarousel";
import { MissionCard } from "./MissionCard";

// Shared by the standalone Missions page and the landing page's own "Missions" tab -- same
// disposition-matchup picker either way.
export function MissionsExplorer() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [layouts, setLayouts] = useState<LayoutMatchup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [yours, setYours] = useState<Disposition>(DISPOSITIONS[0]);
  const [theirs, setTheirs] = useState<Disposition>(DISPOSITIONS[0]);
  const [showMeasurements, setShowMeasurements] = useState(false);

  useEffect(() => {
    api.listPrimaryMissions().then(setMissions).catch((e) => setError(String(e)));
    api.listLayouts().then(setLayouts).catch((e) => setError(String(e)));
  }, []);

  // Reading your own row against their column is deliberately asymmetric -- your opponent
  // declaring a different disposition than you can leave you playing a different Primary
  // Mission than they are, in the same game (confirmed against the real Force Disposition
  // Matrix: Take and Hold vs. Purge the Foe gives you "Immovable Object" while they get
  // "Unstoppable Force" from their own row). Only a same/same pick is a mirror.
  const mission = missions.find((m) => m.deck === yours && m.vs === theirs);
  const opponentMission = missions.find((m) => m.deck === theirs && m.vs === yours);
  const isMirror = yours === theirs;
  const layoutMatchup = layouts.find((l) => l.deck === yours && l.vs === theirs);

  return (
    <>
      <p className="muted">
        Pick both players' declared Force Disposition to see the exact Primary Mission each of
        you would play — read from your own row against your opponent's column, so it can
        differ from theirs in the same game. Reference only (source: gdmissions.app), not tied
        to any battle yet.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="inline-form">
        <label>
          Your disposition
          <select value={yours} onChange={(e) => setYours(e.target.value as Disposition)}>
            {DISPOSITIONS.map((d) => (
              <option key={d} value={d}>
                {DISPOSITION_LABELS[d]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Opponent's disposition
          <select value={theirs} onChange={(e) => setTheirs(e.target.value as Disposition)}>
            {DISPOSITIONS.map((d) => (
              <option key={d} value={d}>
                {DISPOSITION_LABELS[d]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {layoutMatchup && (
        <div className="mission-card">
          <h2>Recommended layout — {layoutMatchup.name}</h2>
          <label>
            <input
              type="checkbox"
              checked={showMeasurements}
              onChange={(e) => setShowMeasurements(e.target.checked)}
            />{" "}
            Show measurements
          </label>
          <LayoutCarousel key={`${layoutMatchup.deck}-${layoutMatchup.vs}`} matchup={layoutMatchup} showMeasurements={showMeasurements} />

          <details className="all-layouts">
            <summary>Browse all layouts</summary>
            <div className="all-layouts-list">
              {layouts.map((m) => (
                <div key={`${m.deck}-${m.vs}`} className="mission-section">
                  <div className="mission-section-header">{m.name}</div>
                  <LayoutCarousel matchup={m} showMeasurements={showMeasurements} />
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

      {mission || opponentMission ? (
        <div className="mission-pair">
          {mission && <MissionCard title="Your mission" mission={mission} />}
          {opponentMission && !isMirror && <MissionCard title="Opponent's mission" mission={opponentMission} />}
        </div>
      ) : (
        !error && missions.length > 0 && <p className="muted">No mission found for that matchup.</p>
      )}
    </>
  );
}
