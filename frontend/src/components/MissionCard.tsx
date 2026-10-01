import { renderAbilityText } from "../markup";
import type { Mission, MissionTier } from "../types";

function tierBadges(tier: MissionTier): string[] {
  const badges: string[] = [];
  if (tier.per_unit) badges.push("per unit");
  if (tier.cumulative) badges.push("cumulative");
  if (tier.kind) badges.push(tier.kind);
  return badges;
}

export function MissionCard({ title, mission }: { title: string; mission: Mission }) {
  return (
    <div className="mission-card">
      <h2>
        {title} — {mission.name}
      </h2>
      {mission.sections.map((section, i) => (
        <div key={i} className="mission-section">
          <div className="mission-section-header">
            {section.when}
            {section.trigger && <span className="muted"> — {section.trigger}</span>}
          </div>
          <ul className="ability-list">
            {section.tiers.map((tier, j) => (
              <li key={j}>
                {renderAbilityText(tier.text, `${mission.name}-${i}-${j}`)} <strong>{tier.vp} VP</strong>
                {tierBadges(tier).map((b) => (
                  <span key={b} className="tag">
                    {b}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {mission.rule && (
        <div className="mission-section mission-reverse">
          <div className="mission-section-header">Reverse</div>
          <p>{renderAbilityText(mission.rule, `${mission.name}-reverse`)}</p>
        </div>
      )}
    </div>
  );
}
