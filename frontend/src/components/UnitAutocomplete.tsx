import { useEffect, useState } from "react";
import { api } from "../api";
import type { UnitDefinition } from "../types";

interface Props {
  onSelect: (unit: UnitDefinition) => void;
}

export function UnitAutocomplete({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UnitDefinition[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const handle = setTimeout(() => {
      setLoading(true);
      api
        .searchUnitDefinitions(query)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  return (
    <div className="autocomplete">
      <input
        type="text"
        placeholder="Search units to add (e.g. Farseer)..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {loading && <div className="autocomplete-status">Searching...</div>}
      {results.length > 0 && (
        <ul className="autocomplete-results">
          {results.map((unit) => (
            <li key={unit.id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(unit);
                  setQuery("");
                  setResults([]);
                }}
              >
                <span className="unit-name">{unit.name}</span>
                <span className="unit-points">{unit.points_cost}pts</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
