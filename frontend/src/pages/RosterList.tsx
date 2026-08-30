import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Roster, RosterImportResult } from "../types";

export function RosterList() {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [name, setName] = useState("");
  const [faction, setFaction] = useState("Aeldari - Craftworlds");
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<RosterImportResult | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();

  function refresh() {
    api.listRosters().then(setRosters).catch((e) => setError(String(e)));
  }

  async function handleDeleteRoster(id: number) {
    try {
      await api.deleteRoster(id);
      setConfirmingDeleteId(null);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(refresh, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const roster = await api.createRoster({ name, faction });
      setName("");
      refresh();
      navigate(`/rosters/${roster.id}`);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setImportResult(null);
    setImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const result = await api.importRoster(data);
      setImportResult(result);
      refresh();
    } catch (e) {
      setError(`Import failed: ${String(e)}`);
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="page">
      <h1>Rosters</h1>
      {error && <p className="error">{error}</p>}

      <form className="inline-form" onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="Roster name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          type="text"
          placeholder="Faction"
          value={faction}
          onChange={(e) => setFaction(e.target.value)}
          required
        />
        <button type="submit">New Roster</button>
      </form>

      <div className="import-panel">
        <label htmlFor="import-file" className="import-label">
          {importing ? "Importing..." : "Import from BattleScribe/NewRecruit JSON"}
        </label>
        <input
          id="import-file"
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          onChange={handleImportFile}
          disabled={importing}
        />
      </div>

      {importResult && (
        <div className="import-summary">
          <p>
            Imported <strong>{importResult.roster.name}</strong> — {importResult.imported.length} unit
            {importResult.imported.length === 1 ? "" : "s"} matched
            {importResult.unmatched.length > 0 && `, ${importResult.unmatched.length} unmatched`}
            {importResult.attachments_created > 0 &&
              `, ${importResult.attachments_created} leader attachment${importResult.attachments_created === 1 ? "" : "s"}`}
            .
          </p>
          {importResult.unmatched.length > 0 && (
            <p className="muted">
              Not found in imported reference data (run the indexer + import script for their faction):{" "}
              {importResult.unmatched.join(", ")}
            </p>
          )}
          <Link to={`/rosters/${importResult.roster.id}`}>Open roster →</Link>
        </div>
      )}

      <ul className="roster-list">
        {rosters.map((r) => (
          <li key={r.id}>
            {confirmingDeleteId === r.id ? (
              <span className="delete-confirm-inline">
                Delete <strong>{r.name}</strong> and everything in it? This can't be undone.{" "}
                <button type="button" className="link-button" onClick={() => handleDeleteRoster(r.id)}>
                  Confirm
                </button>
                <button type="button" className="link-button" onClick={() => setConfirmingDeleteId(null)}>
                  Cancel
                </button>
              </span>
            ) : (
              <>
                <Link to={`/rosters/${r.id}`}>{r.name}</Link>
                <span className="muted"> — {r.faction}</span>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setConfirmingDeleteId(r.id)}
                >
                  delete
                </button>
              </>
            )}
          </li>
        ))}
        {rosters.length === 0 && <li className="muted">No rosters yet.</li>}
      </ul>
    </div>
  );
}
