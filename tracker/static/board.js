// The board: one column per stage, a quick-add form in the start column, cards moved by drag and drop
// or by their Back / Next buttons; a click on a card opens its details.
import { cardCvName } from "./cv.js";
import { h } from "./dom.js";
import { CLOSED_REASONS, daysInStage, isOverdue, isStale } from "./store.js";

// handlers: { onOpen(id), onMove(id, columnId) }
export function bindBoard(board, handlers) {
  board.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (btn) {
      const { action, id, to } = btn.dataset;
      if (action === "open") handlers.onOpen(id);
      else if (action === "move") handlers.onMove(id, to);
      return;
    }
    const card = e.target.closest(".card");
    if (card && !e.target.closest("button, a, input, select, textarea")) handlers.onOpen(card.dataset.id);
  });
  board.addEventListener("dragstart", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    e.dataTransfer.setData("text/plain", card.dataset.id);
    e.dataTransfer.effectAllowed = "move";
    card.classList.add("dragging");
  });
  board.addEventListener("dragend", (e) => e.target.closest(".card")?.classList.remove("dragging"));
  board.addEventListener("dragover", (e) => {
    const col = e.target.closest(".column");
    if (!col) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    col.classList.add("drop-target");
  });
  board.addEventListener("dragleave", (e) => {
    const col = e.target.closest(".column");
    if (col && !col.contains(e.relatedTarget)) col.classList.remove("drop-target");
  });
  board.addEventListener("drop", (e) => {
    const col = e.target.closest(".column");
    if (!col) return;
    e.preventDefault();
    col.classList.remove("drop-target");
    const id = e.dataTransfer.getData("text/plain");
    if (id) handlers.onMove(id, col.dataset.column);
  });
}

// visible: the cards that pass the filter; totals: card count per column before filtering;
// quickAdd: the quick-add form, placed at the top of the start column;
// ctx: { now, r: column roles, variants: for the CV names }.
export function renderBoard(board, columns, visible, totals, quickAdd, ctx) {
  board.replaceChildren(...columns.map((col, i) => {
    const cards = visible.filter((c) => c.column === col.id)
      .sort((a, b) => (a.history.at(-1).date < b.history.at(-1).date ? 1 : -1));
    const total = totals[col.id] || 0;
    const count = cards.length === total ? String(total) : `${cards.length} of ${total}`;
    return h("section", { className: `column${col.kind === "closed" ? " column-closed" : ""}`,
      dataset: { column: col.id }, "aria-labelledby": `col-${col.id}` },
      h("header", { className: "column-head" },
        h("h2", { id: `col-${col.id}` }, col.name),
        h("span", { className: "count", "aria-label": `${count} cards` }, count)),
      col.hint && h("p", { className: "column-hint" }, col.hint),
      col.id === ctx.r.start && quickAdd,
      h("div", { className: "cards" }, cards.length
        ? cards.map((c) => cardView(c, columns[i - 1], columns[i + 1], ctx))
        : h("p", { className: "empty" }, "No cards")));
  }));
}

function cardView(card, prev, next, { now, r, variants }) {
  const stale = isStale(card, now, r);
  const overdue = isOverdue(card, now, r);
  const closed = card.column === r.closed;
  const days = daysInStage(card, now);
  const comments = (card.comments || []).length;
  const cv = cardCvName(card, variants);
  const name = card.company + (card.role ? `, ${card.role}` : "");
  const className = ["card", overdue ? "card-due" : stale ? "card-stale" : "", closed ? "card-closed" : ""]
    .join(" ").trim();
  return h("article", { className, draggable: true, tabIndex: -1, dataset: { id: card.id }, "aria-label": name },
    h("h3", {}, h("button", { type: "button", className: "card-title", dataset: { action: "open", id: card.id },
      "aria-label": `Open ${name}` }, card.company)),
    card.role && h("p", { className: "role" }, card.role),
    cv && h("p", { className: "meta" }, `CV ${cv}`),
    h("p", { className: "badges" },
      h("span", { className: "badge" }, `${days} ${days === 1 ? "day" : "days"} in stage`),
      comments > 0 && h("span", { className: "badge" }, `${comments} ${comments === 1 ? "comment" : "comments"}`),
      closed && h("span", { className: "badge reason" }, CLOSED_REASONS[card.closedReason] || "No outcome"),
      overdue ? h("span", { className: "badge due" }, "Follow up")
        : stale && h("span", { className: "badge stale" }, "Stale")),
    h("div", { className: "card-actions" },
      prev && h("button", { type: "button", dataset: { action: "move", id: card.id, to: prev.id },
        "aria-label": `Move ${name} back to ${prev.name}`, title: `Back to ${prev.name}` }, "\u2190"),
      next && h("button", { type: "button", dataset: { action: "move", id: card.id, to: next.id },
        "aria-label": `Move ${name} to ${next.name}`, title: `Move to ${next.name}` }, "\u2192")));
}

export function focusCard(board, id) {
  board.querySelector(`.card[data-id="${CSS.escape(id)}"] .card-title`)?.focus();
}
