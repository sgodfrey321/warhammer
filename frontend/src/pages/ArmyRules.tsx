import { useEffect, useState } from "react";
import { api } from "../api";
import { ArmyRulesList } from "../components/ArmyRulesList";
import { DetachmentsList } from "../components/DetachmentsList";
import type { FactionArmyRules, FactionDetachments } from "../types";

export function ArmyRules() {
  const [factions, setFactions] = useState<FactionArmyRules[]>([]);
  const [detachments, setDetachments] = useState<FactionDetachments[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listArmyRules().then(setFactions).catch((e) => setError(String(e)));
    api.listDetachments().then(setDetachments).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="page">
      <h1>Army Rules</h1>
      <p className="muted">
        Catalogue/library-level rules and detachments, pulled straight from BSData — not yet tied
        to any roster or battle state, just reference text.
      </p>
      {error && <p className="error">{error}</p>}

      <details className="accordion">
        <summary>Rules</summary>
        <ArmyRulesList factions={factions} />
      </details>

      <details className="accordion">
        <summary>Detachments</summary>
        <DetachmentsList factions={detachments} />
      </details>
    </div>
  );
}
