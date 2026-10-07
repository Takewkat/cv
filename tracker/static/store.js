// Board model: cards, stages and the rules around them. No DOM here.
// Columns come from the document (tracker/store.py holds the one list); a column's kind gives its role:
// "start" where an application enters, "closed" where cards carry an outcome.

// A card is stale when nothing happened on it for more than this many days.
export const STALE_DAYS = 14;

// Same keys as tracker/store.py.
export const CLOSED_REASONS = { accepted: "Accepted", rejected: "Rejected", withdrew: "Withdrew",
  ghosted: "Ghosted", declined: "Offer declined" };

// { start, closed }: the ids of the columns of those kinds.
export function roles(columns) {
  const id = (kind) => columns.find((c) => c.kind === kind)?.id;
  return { start: id("start") || columns[0].id, closed: id("closed") || columns.at(-1).id };
}

// Local date as YYYY-MM-DD.
export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const daysBetween = (from, to) => Math.round((Date.parse(to) - Date.parse(from)) / 86400000);
const stageSince = (card) => card.history.at(-1).date;
export const daysInStage = (card, now) => daysBetween(stageSince(card), now);

// Last day something happened: a move, an edit or a comment.
function lastActivity(card) {
  const days = [stageSince(card), card.touchedOn || "", ...(card.comments || []).map((c) => c.at.slice(0, 10))];
  return days.sort().at(-1);
}

export const isStale = (card, now, r) => card.column !== r.closed && daysBetween(lastActivity(card), now) > STALE_DAYS;
export const isOverdue = (card, now, r) => card.column !== r.closed && !!card.nextDate && card.nextDate < now;

// Started in the start column: an application sent or a first contact, not a later stage.
export const startedAtStart = (card, r) => card.history[0].column === r.start;

// Reached a stage past the start column, or an offer.
export const responded = (card, r) =>
  card.history.some((s) => s.column !== r.start && s.column !== r.closed) ||
  card.closedReason === "accepted" || card.closedReason === "declined";

function newId() {
  return crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
}

// fields: { company, role, profile, variant, cvKind, cvNote }
export function newCard(fields, r) {
  return { id: newId(), ...fields, column: r.start, touchedOn: today(), comments: [],
    history: [{ column: r.start, date: today() }] };
}

// Moves a card and records the stage change with today's date; returns false when it is already there.
export function moveCard(card, column, closedReason, r) {
  if (card.column === column) return false;
  card.column = column;
  card.closedReason = column === r.closed ? closedReason : "";
  card.history.push({ column, date: today() });
  return true;
}

export function updateCard(card, fields) {
  Object.assign(card, fields);
  card.touchedOn = today();
}

// The CV of the card added last, for the quick-add default.
export function lastCv(cards) {
  return [...cards].reverse().find((c) => c.cvKind || (c.profile && c.variant)) || {};
}
