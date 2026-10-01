import { lookupKeyword } from "../coreRules";

// A single keyword/rule tag, hover-explained via the browser's native title tooltip when it's a
// recognized core rule -- deliberately not a custom CSS tooltip: this renders inside table cells
// nested in scrollable containers (.table-scroll, .modal-overlay), where a positioned tooltip
// risks being clipped by an ancestor's overflow. Native tooltips aren't subject to that.
export function Keyword({ name }: { name: string }) {
  const text = lookupKeyword(name);
  if (!text) return <>{name}</>;
  return (
    <span className="keyword-hint" title={text}>
      {name}
    </span>
  );
}

// Renders a comma-separated keyword string (e.g. a weapon's "Keywords" characteristic) as
// individually hoverable Keyword spans.
export function KeywordList({ value }: { value: string }) {
  const parts = value
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) return <>-</>;
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          <Keyword name={p} />
          {i < parts.length - 1 ? ", " : ""}
        </span>
      ))}
    </>
  );
}
