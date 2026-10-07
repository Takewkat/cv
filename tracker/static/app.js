// Entry point: loads the board, applies each change in memory, saves it in order, renders.
import * as api from "./api.js";
import { bindBoard, focusCard, renderBoard } from "./board.js";
import { askOutcome, openDetail } from "./card-detail.js";
import { bindCvFilter, matchesCv, renderCvFilter } from "./cv-filter.js";
import { h } from "./dom.js";
import { bindQuickAdd, fillQuickAdd, quickAdd } from "./quick-add.js";
import { renderStats } from "./stats.js";
import { moveCard, newCard, roles, today, updateCard } from "./store.js";

const $ = (id) => document.getElementById(id);
const board = $("board");
const search = $("search");
const state = { doc: null, variants: [], variantErrors: [], conflict: false };
// Saves run one after another, each with the updatedAt the previous one returned.
let saving = Promise.resolve();

function banner(message, action) {
  const el = $("banner");
  el.replaceChildren(h("span", {}, message),
    ...(action ? [h("button", { type: "button", onclick: action.run }, action.label)] : []));
  el.hidden = false;
}

function status(text) {
  $("save-status").textContent = text;
}

// What the views need besides the cards: today, the columns and their roles, the CVs in profiles/.
const context = () => ({ now: today(), columns: state.doc.columns, r: roles(state.doc.columns), variants: state.variants });

function render() {
  const ctx = context();
  const { cards, columns } = state.doc;
  const q = search.value.trim().toLowerCase();
  const cv = renderCvFilter(state.variants);
  const visible = cards.filter((c) => matchesCv(c, cv) && (!q || `${c.company} ${c.role || ""}`.toLowerCase().includes(q)));
  const totals = {};
  for (const c of cards) totals[c.column] = (totals[c.column] || 0) + 1;
  // The quick-add form is moved into the new start column; it keeps its values, focus is given back.
  const focused = quickAdd.contains(document.activeElement) ? document.activeElement : null;
  fillQuickAdd(state.variants, cards);
  renderStats($("stats"), cards, ctx);
  renderBoard(board, columns, visible, totals, quickAdd, ctx);
  focused?.focus();
}

function save() {
  saving = saving.then(async () => {
    if (state.conflict) return;
    status("Saving...");
    try {
      const { document } = await api.saveState(state.doc);
      state.doc.updatedAt = document.updatedAt;
      status(`Saved ${new Date().toLocaleTimeString()}`);
    } catch (e) {
      status("Not saved");
      if (e instanceof api.ConflictError) {
        state.conflict = true;
        banner("This board was changed elsewhere (another tab, or a synced copy) after you opened it. " +
          "Your last change is not saved. Reload to get the latest version.", { label: "Reload", run: () => location.reload() });
      } else if (e instanceof api.RejectedError) {
        // The server refused this version: go back to the saved one so later changes can save again.
        banner(`Not saved, the last change was undone: ${e.message}.`);
        try {
          state.doc = (await api.loadState()).document;
          render();
        } catch (err) {
          state.conflict = true;
        }
      } else {
        banner(`Not saved: ${e.message}. Your next change retries.`);
      }
    }
  });
  return saving;
}

// Applies a change to the document, then renders and saves.
function change(mutate) {
  if (state.conflict) return false;
  mutate(state.doc);
  render();
  save();
  return true;
}

const findCard = (id) => state.doc.cards.find((c) => c.id === id);

async function move(id, column) {
  const card = findCard(id);
  if (!card || card.column === column) return;
  const r = roles(state.doc.columns);
  let outcome = "";
  if (column === r.closed) {
    outcome = await askOutcome(card.company);
    if (outcome == null) return;
  }
  if (change(() => moveCard(card, column, outcome, r))) focusCard(board, id);
}

async function open(id) {
  const card = findCard(id);
  if (!card) return;
  const result = await openDetail(card, { columns: state.doc.columns, variants: state.variants,
    variantErrors: state.variantErrors, r: roles(state.doc.columns) });
  if (!result) return focusCard(board, id);
  if (result.action === "delete") {
    change((doc) => { doc.cards = doc.cards.filter((c) => c.id !== id); });
  } else if (change(() => updateCard(card, result.fields))) {
    focusCard(board, id);
  }
}

function add(fields) {
  change((doc) => doc.cards.push(newCard(fields, roles(doc.columns))));
}

function bindControls() {
  bindBoard(board, { onOpen: open, onMove: move });
  bindQuickAdd(add);
  search.addEventListener("input", render);
  bindCvFilter(render);
}

async function main() {
  try {
    const res = await api.loadState();
    state.doc = res.document;
    $("data-path").textContent = res.dataPath;
  } catch (e) {
    return banner(`The board did not load: ${e.message}`);
  }
  bindControls();
  render();
  try {
    const { variants, errors } = await api.loadVariants();
    Object.assign(state, { variants, variantErrors: errors });
    render();
  } catch (e) {
    state.variantErrors = [e.message];
  }
}

main();
