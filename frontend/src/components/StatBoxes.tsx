// Shared by UnitsBrowser.tsx and RosterEditor.tsx's Available Units panel -- one boxed pill per
// stat/weapon characteristic, instead of a plain space-joined monospace string.
export function StatBoxes({ pairs }: { pairs: { label: string; value: React.ReactNode }[] }) {
  if (pairs.length === 0) return null;
  return (
    <span className="stat-boxes">
      {pairs.map((p) => (
        <span key={p.label} className="stat-box">
          <span className="stat-box-label">{p.label}</span>
          <span className="stat-box-value">{p.value}</span>
        </span>
      ))}
    </span>
  );
}
