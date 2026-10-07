// "CV sent": select values and the names shown for them.
// A value is "<profile>/<variant>" (ids, so renaming a label keeps the cards), "other", or "" (not recorded).

export const OTHER = "other";

export function cvValue(card) {
  if (card.cvKind === OTHER) return OTHER;
  return card.profile && card.variant ? `${card.profile}/${card.variant}` : "";
}

// Card fields for a select value.
export function cvFields(value, note) {
  if (value === OTHER) return { profile: "", variant: "", cvKind: OTHER, cvNote: note };
  const [profile = "", variant = ""] = value ? value.split("/") : [];
  return { profile, variant, cvKind: "", cvNote: "" };
}

// [value, name] for every variant of GET /api/variants ({profile, variant, label}; the server builds the label).
export const cvOptions = (variants) => variants.map((v) => [`${v.profile}/${v.variant}`, v.label]);

export function cvName(value, variants) {
  if (value === OTHER) return "Other";
  if (!value) return "";
  return cvOptions(variants).find(([v]) => v === value)?.[1] || value.replace("/", " / ");
}

// The name shown on a card: "Other" carries its note.
export function cardCvName(card, variants) {
  const name = cvName(cvValue(card), variants);
  return card.cvKind === OTHER && card.cvNote ? `${name}: ${card.cvNote}` : name;
}
