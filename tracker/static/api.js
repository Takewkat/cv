// Calls to tracker/server.py. Errors carry the server's message; a 409 is a ConflictError, any other refusal
// a RejectedError (the server answered no), a network failure a plain Error (worth retrying).

export class ConflictError extends Error {}
export class RejectedError extends Error {}

async function call(method, url, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new Error("the tracker server does not answer; is ./tracker.sh still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 409) throw new ConflictError(data.error || "the board changed elsewhere");
  if (!res.ok) throw new RejectedError(data.error || `${method} ${url}: HTTP ${res.status}`);
  return data;
}

export const loadState = () => call("GET", "/api/state");
export const saveState = (doc) => call("PUT", "/api/state", doc);
export const loadVariants = () => call("GET", "/api/variants");
export const checkGap = (profile, variant, posting) => call("POST", "/api/gap", { profile, variant, posting });
