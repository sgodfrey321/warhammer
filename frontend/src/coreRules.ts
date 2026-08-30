// Hand-authored short paraphrases of core (edition-wide) Warhammer 40k special rules and weapon
// abilities -- NOT verbatim rulebook text. BSData only ever tags a unit/weapon with the rule's
// *name* (confirmed against every faction currently indexed); the definition itself lives only
// in the Core Rules booklet, which nothing in this app's pipeline scrapes. This is the one place
// that text is captured, purely so keyword tags can carry a hover explanation.
//
// Faction-specific rules (Battle Focus, Oath of Moment, Templar Vows, etc.) are deliberately NOT
// here -- their full text is already indexed per-faction in army-rules.json (see the Army Rules
// page), just not yet cross-referenced against a roster's own faction. A tag that isn't a core
// rule simply renders without a tooltip, same as before this file existed.

const EXACT_RULES: Record<string, string> = {
  // Weapon abilities
  assault: "This weapon can still be fired by a model even if that model Advanced this turn.",
  blast: "This weapon's Attacks characteristic gets +1 for every full 5 models in the target unit.",
  "close-quarters": "This weapon cannot be used to make attacks against a unit that isn't within Engagement Range.",
  conversion: "This weapon's AP improves the further the shooting model is from its target.",
  "devastating wounds":
    "Each Critical Wound this weapon inflicts (an unmodified wound roll of 6, unless stated otherwise) is resolved as a mortal wound equal to the Damage rolled, instead of a normal save being made.",
  "extra attacks":
    "This weapon doesn't use the model's Attacks characteristic -- attacks made with it are made in addition to attacks made with the model's other weapons.",
  hazardous:
    "After this weapon is used to shoot or fight, roll a D6 for each model that used it: on a 1, that model's unit suffers a mortal wound (or is destroyed, per the datasheet).",
  heavy: "A model firing this weapon gets +1 to Hit rolls if it Remained Stationary this turn.",
  "ignores cover": "The target unit does not receive the Benefit of Cover against this weapon's attacks.",
  "indirect fire":
    "This weapon can target a unit that isn't visible to the firer, but such attacks suffer a -1 to Hit and the target gets the Benefit of Cover.",
  lance: "A model gets +1 to Hit rolls for this weapon if the attacking model's unit made a Charge move this turn.",
  "lethal hits": "Each unmodified Hit roll of 6 for this weapon automatically wounds the target, without needing a wound roll.",
  "one shot": "This weapon can only be shot once per battle.",
  pistol: "This weapon can be shot even if the firing model's unit is within Engagement Range of an enemy unit, and can target a unit within Engagement Range.",
  precision: "Attacks made with this weapon can be allocated to a Character model within an Attached unit, even if that Character isn't the closest model.",
  psychic: "This attack is a Psychic Attack -- some abilities specifically boost or protect against attacks with this keyword.",
  torrent: "This weapon automatically hits its target -- no Hit roll is made.",
  "twin-linked": "You can re-roll Wound rolls for this weapon.",
  "twin linked": "You can re-roll Wound rolls for this weapon.",
  "special issue ammunition": "This weapon can instead be shot as one of several listed alternative ammunition profiles, per the datasheet.",

  // Unit abilities
  "deadly demise": "When a model with this ability is destroyed, roll a D6 (or as stated): on a 6, each unit within 6\" suffers mortal wounds.",
  "deep strike": "This unit can be set up in Strategic Reserves and, when it arrives, can be set up anywhere on the battlefield more than 9\" from all enemy models.",
  "feel no pain": "Each time a model with this ability would lose a wound, roll a D6: on the stated value or better, that wound is not lost.",
  "fights first": "This unit's models fight in the Fight phase before any unit that doesn't have this ability, regardless of charge order.",
  "firing deck": "While a friendly unit is embarked within this TRANSPORT, up to the stated number of its models can shoot as if disembarked, without the transport itself shooting.",
  hover: "This model is treated as an Aircraft for movement purposes (it can move over other models and terrain) despite not otherwise having the Aircraft keyword.",
  infiltrators: "This unit can be set up anywhere on the battlefield that is more than 9\" from the enemy deployment zone and all enemy models, instead of in its owning player's deployment zone.",
  leader: "This unit can be attached to one of the Bodyguard units listed on its datasheet to form a single Attached unit.",
  "lone operative": "This unit can only be selected as the target of a ranged attack if the attacking model is within 12\" of it.",
  scouts: "Before the battle begins, after normal deployment, this unit can make a Normal, Advance, or Fall Back move of the stated distance.",
  stealth: "Each attack that targets this unit suffers a -1 penalty to its Hit roll.",
  "super-heavy walker": "This model uses the Titanic and Walker rules together (explosion radius, structure damage tiers, etc.) as detailed on its datasheet.",
};

// Weapon-keyword variants that carry a numeric/dice value (e.g. "Melta 2", "Rapid Fire 1",
// "Sustained Hits D3") -- the base phrase is matched after stripping the trailing value, and the
// value is spliced back into the description.
const VALUED_RULES: Record<string, (value: string) => string> = {
  melta: (n) => `Inflicts ${n} additional points of Damage against a target that's within half this weapon's range.`,
  "rapid fire": (n) =>
    `This weapon's Attacks characteristic gets +${n} when targeting a unit that's within half this weapon's range.`,
  "sustained hits": (n) =>
    `Each unmodified Hit roll of 6 for this weapon scores ${n} additional hit(s) on the target, resolved at the same time.`,
};

function normalize(raw: string): string {
  return raw
    .replace(/[‐-―−]/g, "-") // unicode hyphen/dash variants (e.g. "Anti-non‑Monster") -> ascii "-"
    .replace(/\s+/g, " ")
    .trim();
}

function properCase(s: string): string {
  return s.replace(/[a-z]+/gi, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
}

// Looks up the meaning of a single keyword/rule tag (not a comma-separated list -- split that
// first). Returns undefined for anything not a recognized core rule, including every
// faction-specific rule name -- callers should render those exactly as before, with no tooltip.
export function lookupKeyword(raw: string): string | undefined {
  const cleaned = normalize(raw).replace(/:.*$/, "").trim();
  const lower = cleaned.toLowerCase();

  if (EXACT_RULES[lower]) return EXACT_RULES[lower];

  const antiMatch = lower.match(/^anti[- ](.+?)\s+(\d+)\+$/);
  if (antiMatch) {
    const [, type, threshold] = antiMatch;
    return `Scores a Critical Wound against ${properCase(type)} models on an unmodified wound roll of ${threshold}+ or more (always at least a success, regardless of the target's normal wound requirement).`;
  }

  const valuedMatch = lower.match(/^(.*?)\s+(d?\d+\+?)$/);
  if (valuedMatch) {
    const [, base, value] = valuedMatch;
    if (VALUED_RULES[base]) return VALUED_RULES[base](value.toUpperCase());
    if (EXACT_RULES[base]) return EXACT_RULES[base];
  }

  return undefined;
}
