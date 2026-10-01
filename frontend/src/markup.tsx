import { Fragment } from "react";

// GW/BattleScribe ability text markup, confirmed against real indexer output: "**bold**" is
// plain markdown bold; "^^keyword^^" is GW's own convention for a keyword being referenced
// (not a real hyperlink -- there's no per-keyword rules page in this data -- but visually
// distinct all the same). The two combine, but not always in the same order -- unit ability
// text tends to write "**^^Dire Avengers^^**" (bold outer), while army-rule text commonly
// writes "^^**World Eaters^^**" (keyword outer, confirmed in 27 of 57 indexed army rules) --
// so this just toggles bold/keyword state per delimiter run into the text rather than
// assuming either one nests inside the other.
export function renderAbilityText(text: string, keyPrefix = "n"): React.ReactNode[] {
  const parts = text.split(/(\*\*|\^\^)/);
  let bold = false;
  let keyword = false;
  const nodes: React.ReactNode[] = [];
  parts.forEach((part, i) => {
    if (part === "**") {
      bold = !bold;
      return;
    }
    if (part === "^^") {
      keyword = !keyword;
      return;
    }
    if (!part) return;
    let node: React.ReactNode = part;
    if (keyword) node = <span className="ability-keyword">{node}</span>;
    if (bold) node = <strong>{node}</strong>;
    nodes.push(<Fragment key={`${keyPrefix}-${i}`}>{node}</Fragment>);
  });
  return nodes;
}
