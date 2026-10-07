// The quick-add form at the top of the start column: company, role, CV sent; Enter adds the card.
import { OTHER, cvFields, cvOptions, cvValue } from "./cv.js";
import { setOptions } from "./dom.js";
import { lastCv } from "./store.js";

export const quickAdd = document.getElementById("quick-add");
const cv = quickAdd.elements.cv;

// onAdd({ company, role, profile, variant, cvKind, cvNote })
export function bindQuickAdd(onAdd) {
  cv.addEventListener("change", () => { cv.dataset.chosen = cv.value; });
  quickAdd.addEventListener("submit", (e) => {
    e.preventDefault();
    const company = quickAdd.elements.company.value.trim();
    if (!company) return;
    cv.dataset.chosen = cv.value;
    onAdd({ company, role: quickAdd.elements.role.value.trim(), ...cvFields(cv.value, "") });
    quickAdd.elements.company.value = "";
    quickAdd.elements.role.value = "";
  });
}

// The CV select defaults to the CV picked last here, else the CV of the card added last.
export function fillQuickAdd(variants, cards) {
  const chosen = cv.dataset.chosen ?? cvValue(lastCv(cards));
  setOptions(cv, [["", "Not recorded"], ...cvOptions(variants), [OTHER, "Other"]], chosen);
}
