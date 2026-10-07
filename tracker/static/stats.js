// The stats line under the header: applications, response rate, inbound count, conversion per CV sent.
import { cvName, cvValue } from "./cv.js";
import { responded, startedAtStart } from "./store.js";

const pct = (n, d) => (d ? `${Math.round((100 * n) / d)}%` : "-");

// ctx: { r: column roles, variants: the CVs in profiles/ }
function computeStats(cards, { r, variants }) {
  const sent = cards.filter((c) => startedAtStart(c, r));
  const perCv = new Map();
  for (const c of cards) {
    const value = cvValue(c);
    const row = perCv.get(value) || { cv: cvName(value, variants) || "CV not recorded", sent: 0, screened: 0 };
    row.sent += 1;
    row.screened += responded(c, r) ? 1 : 0;
    perCv.set(value, row);
  }
  return {
    total: cards.length,
    sent: sent.length,
    responded: sent.filter((c) => responded(c, r)).length,
    inbound: cards.filter((c) => c.inbound).length,
    perCv: [...perCv.values()].sort((a, b) => b.sent - a.sent),
  };
}

// ctx: { columns, r, variants }
export function renderStats(el, cards, ctx) {
  const s = computeStats(cards, ctx);
  if (!s.total) return void (el.textContent = "No applications yet: add one at the top of the first column.");
  const start = ctx.columns.find((c) => c.id === ctx.r.start)?.name || "the first stage";
  el.textContent = [
    `${s.total} ${s.total === 1 ? "application" : "applications"}`,
    `${pct(s.responded, s.sent)} got past ${start} (${s.responded} of ${s.sent})`,
    `${s.inbound} inbound`,
    ...s.perCv.map((row) => `${row.cv}: ${row.screened} of ${row.sent} past ${start}`),
  ].join("  \u00b7  ");
}
