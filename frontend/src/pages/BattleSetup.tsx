import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { LayoutCarousel } from "../components/LayoutCarousel";
import { MissionCard } from "../components/MissionCard";
import { findMatchup, findMission } from "../missions";
import { DISPOSITIONS, DISPOSITION_LABELS } from "../types";
import type { Disposition, LayoutMatchup, Mission, Roster } from "../types";

export function BattleSetup() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const rosterId = params.get("rosterId") ? Number(params.get("rosterId")) : null;
  const battleId = params.get("battleId") ? Number(params.get("battleId")) : null;
  const mode: "roster" | "battle" = battleId !== null ? "battle" : "roster";

  const [roster, setRoster] = useState<Roster | null>(null);
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [currentRosterId, setCurrentRosterId] = useState<number | null>(rosterId);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [layouts, setLayouts] = useState<LayoutMatchup[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [opponentName, setOpponentName] = useState("");
  const [opponentRosterId, setOpponentRosterId] = useState<number | null>(null);
  // An explicit pick (or a loaded battle's value) wins; otherwise a new battle defaults to each
  // chosen roster's preferred disposition.
  const [yoursPick, setYours] = useState<Disposition | null>(null);
  const [theirsPick, setTheirs] = useState<Disposition | null>(null);
  const [layoutNumber, setLayoutNumber] = useState(1);
  const [showMeasurements, setShowMeasurements] = useState(false);

  useEffect(() => {
    api.listPrimaryMissions().then(setMissions).catch((e) => setError(String(e)));
    api.listLayouts().then(setLayouts).catch((e) => setError(String(e)));
    api.listRosters().then(setRosters).catch((e) => setError(String(e)));
    if (mode === "roster" && rosterId !== null) {
      api.getRoster(rosterId).then(setRoster).catch((e) => setError(String(e)));
    }
    if (mode === "battle" && battleId !== null) {
      api
        .getBattle(battleId)
        .then((b) => {
          setCurrentRosterId(b.roster_id);
          setOpponentName(b.opponent_name ?? "");
          setOpponentRosterId(b.opponent_roster_id ?? null);
          if (b.your_disposition) setYours(b.your_disposition);
          if (b.opponent_disposition) setTheirs(b.opponent_disposition);
          if (b.layout_number) setLayoutNumber(b.layout_number);
        })
        .catch((e) => setError(String(e)));
    }
  }, [mode, rosterId, battleId]);

  const rosterDisposition = (id: number | null) =>
    mode === "roster" ? (rosters.find((x) => x.id === id)?.disposition ?? null) : null;
  const yours = yoursPick ?? rosterDisposition(currentRosterId) ?? DISPOSITIONS[0];
  const theirs = theirsPick ?? rosterDisposition(opponentRosterId) ?? DISPOSITIONS[0];

  function handleYoursChange(value: Disposition) {
    setYours(value);
    setLayoutNumber(1);
  }

  function handleTheirsChange(value: Disposition) {
    setTheirs(value);
    setLayoutNumber(1);
  }

  async function handleBegin() {
    const payload = {
      opponent_name: opponentName.trim() || null,
      opponent_roster_id: opponentRosterId,
      your_disposition: yours,
      opponent_disposition: theirs,
      layout_number: layoutNumber,
    };
    try {
      if (mode === "roster" && currentRosterId !== null) {
        const created = await api.createBattle({ roster_id: currentRosterId, ...payload });
        navigate(`/battles/${created.id}`);
      } else if (battleId !== null) {
        await api.updateBattleSetup(battleId, payload);
        navigate(`/battles/${battleId}`);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleSkip() {
    if (currentRosterId === null) return;
    try {
      const created = await api.createBattle({ roster_id: currentRosterId });
      navigate(`/battles/${created.id}`);
    } catch (e) {
      setError(String(e));
    }
  }

  const opponentRosterOptions = rosters.filter((r) => r.id !== currentRosterId);

  const mission = findMission(missions, yours, theirs);
  const opponentMission = findMission(missions, theirs, yours);
  const isMirror = yours === theirs;
  const layoutMatchup = findMatchup(layouts, yours, theirs);

  return (
    <div className="page">
      <h1>Battle Setup</h1>
      <p className="muted">
        {mode === "roster" && roster && `Starting a battle for ${roster.name}. `}
        {mode === "battle" && `Editing setup for Battle #${battleId}. `}
        Declare both players' Force Disposition to see each side's Primary Mission and a
        recommended deployment layout. Everything here is optional and can be changed later.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="inline-form">
        {mode === "roster" && rosterId === null && (
          <label>
            Your roster
            <select
              value={currentRosterId ?? ""}
              onChange={(e) => setCurrentRosterId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Select your roster...</option>
              {rosters.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.faction})
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Opponent roster
          <select
            value={opponentRosterId ?? ""}
            onChange={(e) => {
              const id = e.target.value ? Number(e.target.value) : null;
              setOpponentRosterId(id);
              // Auto-fill the label from the chosen roster (unless the player already typed one).
              const picked = rosters.find((r) => r.id === id);
              if (picked && !opponentName.trim()) setOpponentName(picked.name);
            }}
          >
            <option value="">None (name only)</option>
            {opponentRosterOptions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} ({r.faction})
              </option>
            ))}
          </select>
        </label>
        <label>
          Opponent name
          <input
            type="text"
            value={opponentName}
            onChange={(e) => setOpponentName(e.target.value)}
            placeholder="e.g. Steve's Orks"
          />
        </label>
        <label>
          Your disposition
          <select value={yours} onChange={(e) => handleYoursChange(e.target.value as Disposition)}>
            {DISPOSITIONS.map((d) => (
              <option key={d} value={d}>
                {DISPOSITION_LABELS[d]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Opponent's disposition
          <select value={theirs} onChange={(e) => handleTheirsChange(e.target.value as Disposition)}>
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
          <h2>Layout — {layoutMatchup.name}</h2>
          <label>
            <input
              type="checkbox"
              checked={showMeasurements}
              onChange={(e) => setShowMeasurements(e.target.checked)}
            />{" "}
            Show measurements
          </label>
          <LayoutCarousel
            key={`${layoutMatchup.deck}-${layoutMatchup.vs}`}
            matchup={layoutMatchup}
            showMeasurements={showMeasurements}
          >
            {(currentLayoutNumber) => (
              <button
                type="button"
                className={`layout-pick-button${layoutNumber === currentLayoutNumber ? " selected" : ""}`}
                onClick={() => setLayoutNumber(currentLayoutNumber)}
              >
                {layoutNumber === currentLayoutNumber ? "✓ Selected" : "Use this layout"}
              </button>
            )}
          </LayoutCarousel>
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

      <div className="battle-setup-actions">
        <button
          type="button"
          className="primary"
          onClick={handleBegin}
          disabled={mode === "roster" && currentRosterId === null}
        >
          {mode === "roster" ? "Begin Battle" : "Save Setup"}
        </button>
        {mode === "roster" && (
          <button type="button" onClick={handleSkip} disabled={currentRosterId === null}>
            Start without a mission
          </button>
        )}
        {mode === "battle" && (
          <button type="button" onClick={() => navigate(`/battles/${battleId}`)}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
