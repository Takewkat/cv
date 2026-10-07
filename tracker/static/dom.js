// DOM helpers: elements are built from data with text nodes, never innerHTML.

// h("button", { className: "x", "aria-label": "..." }, "text", child) -> element
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("aria-") || k === "role") el.setAttribute(k, v);
    else el[k] = v;
  }
  for (const c of children.flat()) {
    if (c != null && c !== false && c !== "") el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

// Replaces the options of a select with [value, label] pairs and selects value when present.
export function setOptions(select, pairs, value) {
  select.replaceChildren(...pairs.map(([v, label]) => h("option", { value: v }, label)));
  select.value = pairs.some(([v]) => v === value) ? value : pairs.length ? pairs[0][0] : "";
}
