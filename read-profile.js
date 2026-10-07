// Reads profiles/<id>/content.js the way index.html does and checks its shape.
// Usage: node read-profile.js <id>            -> the profile as JSON
//        node read-profile.js <id> --summary  -> "<fileStem> <variant> <variant> ..." for build.sh
const fs = require("fs"), path = require("path"), vm = require("vm");

const ROOT = __dirname;
const SAFE = /^[A-Za-z0-9._-]+$/;
const VARIANT_KEYS = ["name", "headline", "tagline", "profile", "skills", "experience", "education", "contact"];
const LABEL_MAX = 40;

function fail(msg) {
  process.stderr.write("read-profile: " + msg + "\n");
  process.exit(1);
}

function load(id) {
  if (!id || !SAFE.test(id)) fail(`profile id ${JSON.stringify(id || "")} must be a directory name under profiles/`);
  const file = path.join(ROOT, "profiles", id, "content.js");
  if (!fs.existsSync(file)) fail(`${path.relative(ROOT, file)} not found`);
  const ctx = { window: {} };
  try {
    vm.runInNewContext(fs.readFileSync(file, "utf8"), ctx, { filename: file });
  } catch (e) {
    fail(`${path.relative(ROOT, file)}: ${e.message}`);
  }
  const p = ctx.window.PROFILE;
  if (!p || typeof p !== "object") fail(`${path.relative(ROOT, file)} does not set window.PROFILE`);
  return [file, p];
}

function errors(id, p) {
  const out = [];
  if (!SAFE.test(p.theme || "")) out.push("theme must be a theme id, e.g. \"classic\"");
  else if (!fs.existsSync(path.join(ROOT, "themes", p.theme + ".css"))) out.push(`themes/${p.theme}.css not found`);
  if (!SAFE.test(p.fileStem || "")) out.push("fileStem must be letters, digits, dot, dash or underscore, e.g. \"CV-Alex-Martin\"");
  if (p.photo != null && !fs.existsSync(path.join(ROOT, "profiles", id, p.photo))) {
    process.stderr.write(`read-profile: warning: profiles/${id}/${p.photo} not found, the initials are shown instead\n`);
  }
  const variants = p.variants && typeof p.variants === "object" ? Object.keys(p.variants) : [];
  if (!variants.length) out.push("variants must hold at least one variant, e.g. { main: {...} }");
  for (const v of variants) {
    if (!SAFE.test(v)) out.push(`variant id ${JSON.stringify(v)} must be letters, digits, dot, dash or underscore`);
    if (!p.variants[v] || typeof p.variants[v] !== "object") { out.push(`variant ${v} must be an object`); continue; }
    const missing = VARIANT_KEYS.filter((k) => p.variants[v][k] == null);
    if (missing.length) out.push(`variant ${v} misses ${missing.join(", ")}`);
    else if (!p.variants[v].contact.email) out.push(`variant ${v} misses contact.email`);
    const label = p.variants[v].label;
    if (label != null && (typeof label !== "string" || !label.trim() || label.length > LABEL_MAX)) {
      out.push(`variant ${v} label must be a short text of 1 to ${LABEL_MAX} characters, e.g. "SRE / Platform"`);
    }
  }
  return out;
}

const [id, flag] = process.argv.slice(2);
const [file, p] = load(id);
const problems = errors(id, p);
if (problems.length) fail(path.relative(ROOT, file) + ":\n  " + problems.join("\n  "));
process.stdout.write(flag === "--summary" ? [p.fileStem, ...Object.keys(p.variants)].join(" ") + "\n" : JSON.stringify(p));
