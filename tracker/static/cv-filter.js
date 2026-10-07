// The CV filter: toggle chips "All", one per CV in profiles/, "Other"; the choice is remembered in this browser.
import { OTHER, cvOptions, cvValue } from "./cv.js";
import { h } from "./dom.js";

const KEY = "tracker.cvFilter";
const box = document.getElementById("cv-filter");
let chosen = "";
try {
  chosen = localStorage.getItem(KEY) || "";
} catch (e) {
  chosen = "";
}

export function bindCvFilter(onChange) {
  box.addEventListener("click", (e) => {
    const chip = e.target.closest("button[data-cv]");
    if (!chip) return;
    chosen = chip.dataset.cv;
    try {
      localStorage.setItem(KEY, chosen);
    } catch (err) {
      // Storage refused (private window): the choice lasts until reload.
    }
    onChange();
  });
}

// Draws the chips and returns the active value; a remembered CV that is no longer listed shows All.
export function renderCvFilter(variants) {
  const chips = [["", "All"], ...cvOptions(variants), [OTHER, "Other"]];
  const active = chips.some(([v]) => v === chosen) ? chosen : "";
  const focused = box.contains(document.activeElement) ? document.activeElement.dataset.cv : null;
  box.replaceChildren(...chips.map(([value, label]) => h("button", { type: "button", className: "chip",
    dataset: { cv: value }, "aria-pressed": String(value === active) }, label)));
  if (focused != null) box.querySelector(`button[data-cv="${CSS.escape(focused)}"]`)?.focus();
  return active;
}

export const matchesCv = (card, active) => !active || cvValue(card) === active;
