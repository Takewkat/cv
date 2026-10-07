// The card details dialog: company, role and CV sent, then the comments; job link, recruiter flag, next step date,
// outcome, posting text with the gap check and the stage history under "More". Plus the one-click outcome prompt.
import { checkGap } from "./api.js";
import { OTHER, cvFields, cvName, cvOptions, cvValue } from "./cv.js";
import { h, setOptions } from "./dom.js";
import { CLOSED_REASONS } from "./store.js";

const dialog = document.getElementById("detail");
const form = document.getElementById("detail-form");
const gapButton = document.getElementById("gap-check");
const gapStatus = document.getElementById("gap-status");
const gapOutput = document.getElementById("gap-output");
const outcomeDialog = document.getElementById("outcome-dialog");

const TEXT_FIELDS = ["company", "role", "url", "nextDate", "posting"];
let finish = null;
let company = "";
// Working copy of the card's comments; written back on Save.
let comments = [];

// Resolves to { action: "save", fields }, { action: "delete" } or null (cancelled).
export function openDetail(card, { columns, variants, variantErrors, r }) {
  document.getElementById("detail-title").textContent = card.company;
  company = card.company;
  for (const name of TEXT_FIELDS) form.elements[name].value = card[name] || "";
  form.elements.inbound.checked = !!card.inbound;
  form.elements.cvNote.value = card.cvNote || "";
  setOptions(form.elements.closedReason, [["", "Not set"], ...Object.entries(CLOSED_REASONS)], card.closedReason || "");
  document.getElementById("outcome-field").hidden = card.column !== r.closed;
  fillCv(card, variants, variantErrors);
  comments = (card.comments || []).map((c) => ({ ...c }));
  form.elements.newComment.value = "";
  renderComments();
  renderHistory(card, columns);
  form.querySelector("details").open = false;
  gapOutput.hidden = true;
  gapOutput.textContent = "";
  gapStatus.textContent = "";
  dialog.showModal();
  form.elements.newComment.focus();
  return new Promise((resolve) => { finish = resolve; });
}

function fillCv(card, variants, errors) {
  const options = [["", "Not recorded"], ...cvOptions(variants)];
  const current = cvValue(card);
  if (current && current !== OTHER && !options.some(([v]) => v === current)) {
    options.push([current, `${cvName(current, variants)} (not in profiles/ any more)`]);
  }
  options.push([OTHER, "Other (a CV outside this repo)"]);
  setOptions(form.elements.cv, options, current);
  document.getElementById("cv-errors").textContent = errors.length ? `Some profiles did not load: ${errors.join("; ")}` : "";
  showCvNote();
}

function showCvNote() {
  const value = form.elements.cv.value;
  document.getElementById("cv-note-field").hidden = value !== OTHER;
  gapButton.disabled = !value || value === OTHER;
  gapButton.title = gapButton.disabled ? "Pick a CV from profiles/ to compare the posting with" : "";
}

const formatAt = (at) => new Date(at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

// Newest first; each item keeps the index of its comment in the working copy.
function renderComments() {
  const order = comments.map((c, i) => i).sort((a, b) => (comments[a].at < comments[b].at ? 1 : -1));
  document.getElementById("comments-list").replaceChildren(...order.map((i) => {
    const c = comments[i];
    return h("li", { dataset: { index: i } },
      h("div", { className: "comment-head" },
        h("time", { dateTime: c.at }, formatAt(c.at)),
        h("button", { type: "button", className: "link", dataset: { comment: "edit" },
          "aria-label": `Edit the comment of ${formatAt(c.at)}` }, "Edit"),
        h("button", { type: "button", className: "link", dataset: { comment: "delete" },
          "aria-label": `Delete the comment of ${formatAt(c.at)}` }, "Delete")),
      h("p", { className: "comment-text" }, c.text));
  }));
  document.getElementById("comments-count").textContent = comments.length ? ` (${comments.length})` : "";
}

function addComment() {
  const text = form.elements.newComment.value.trim();
  if (!text) return;
  comments.push({ at: new Date().toISOString(), text });
  form.elements.newComment.value = "";
  renderComments();
}

function onCommentClick(e) {
  const btn = e.target.closest("button[data-comment]");
  if (!btn) return;
  const li = btn.closest("li");
  const i = Number(li.dataset.index);
  const action = btn.dataset.comment;
  if (action === "edit") {
    const area = h("textarea", { rows: 3, maxLength: 5000, value: comments[i].text, "aria-label": "Comment text" });
    li.querySelector(".comment-text").replaceWith(h("div", { className: "comment-edit" }, area,
      h("button", { type: "button", dataset: { comment: "done" } }, "Done"),
      h("button", { type: "button", dataset: { comment: "cancel" } }, "Cancel")));
    area.focus();
    return;
  }
  if (action === "delete" && confirm("Delete this comment?")) comments.splice(i, 1);
  if (action === "done") {
    const text = li.querySelector("textarea").value.trim();
    if (text) comments[i].text = text;
  }
  renderComments();
}

function renderHistory(card, columns) {
  const name = (id) => columns.find((c) => c.id === id)?.name || id;
  document.getElementById("history").replaceChildren(h("h3", {}, "Stage history"),
    h("ol", {}, card.history.map((s) => h("li", {}, h("time", { dateTime: s.date }, s.date), ` ${name(s.column)}`))));
}

function done(result) {
  const resolve = finish;
  finish = null;
  if (dialog.open) dialog.close();
  resolve?.(result);
}

// Keeps the text of comment edits still open, as if Done was clicked.
function commitEdits() {
  for (const area of document.querySelectorAll("#comments-list textarea")) {
    const text = area.value.trim();
    if (text) comments[Number(area.closest("li").dataset.index)].text = text;
  }
}

function read() {
  const fields = {};
  for (const name of TEXT_FIELDS) fields[name] = form.elements[name].value.trim();
  fields.company ||= company;
  fields.inbound = form.elements.inbound.checked;
  Object.assign(fields, cvFields(form.elements.cv.value, form.elements.cvNote.value.trim()));
  if (!document.getElementById("outcome-field").hidden) fields.closedReason = form.elements.closedReason.value;
  commitEdits();
  addComment();
  fields.comments = comments.map((c) => ({ at: c.at, text: c.text }));
  return { action: "save", fields };
}

async function runGap() {
  const [profile, variant] = form.elements.cv.value.split("/");
  const posting = form.elements.posting.value;
  if (!posting.trim()) return void (gapStatus.textContent = "Paste the posting text first.");
  gapButton.disabled = true;
  gapStatus.textContent = "Checking...";
  try {
    const { output } = await checkGap(profile, variant, posting);
    gapOutput.textContent = output;
    gapOutput.hidden = false;
    gapStatus.textContent = "";
  } catch (e) {
    gapStatus.textContent = `Gap check failed: ${e.message}`;
  } finally {
    showCvNote();
  }
}

form.elements.cv.addEventListener("change", showCvNote);
form.addEventListener("submit", (e) => {
  e.preventDefault();
  done(read());
});
document.getElementById("detail-cancel").addEventListener("click", () => done(null));
document.getElementById("delete-card").addEventListener("click", () => {
  if (confirm(`Delete ${form.elements.company.value || "this application"}? The previous file stays in backups/.`)) {
    done({ action: "delete" });
  }
});
dialog.addEventListener("close", () => done(null));
gapButton.addEventListener("click", runGap);
document.getElementById("add-comment").addEventListener("click", addComment);
document.getElementById("comments-list").addEventListener("click", onCommentClick);

// One button per outcome; resolves to its key, or null when cancelled.
const outcomes = document.getElementById("outcomes");
outcomes.replaceChildren(...Object.entries(CLOSED_REASONS).map(([key, label]) =>
  h("button", { type: "submit", value: key }, label)));

export function askOutcome(company) {
  document.getElementById("outcome-company").textContent = company;
  outcomeDialog.returnValue = "";
  outcomeDialog.showModal();
  outcomes.querySelector("button").focus();
  return new Promise((resolve) => {
    outcomeDialog.addEventListener("close", () => resolve(outcomeDialog.returnValue || null), { once: true });
  });
}
