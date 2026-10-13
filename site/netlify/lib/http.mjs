// Small shared helpers for every function. No dependencies.

export class HttpError extends Error {
  constructor(status, code, extra = {}) {
    super(code);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

export function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

/** Wrap a handler so every error becomes a clean JSON response (and real errors are logged, not leaked). */
export function handle(fn) {
  return async (req, context) => {
    try {
      return await fn(req, context);
    } catch (err) {
      if (err instanceof HttpError) return json(err.status, { error: err.code, ...err.extra });
      console.error("Unhandled function error:", err && err.stack ? err.stack : err);
      return json(500, { error: "server_error" });
    }
  };
}

export function requireMethod(req, method) {
  if (req.method !== method) throw new HttpError(405, "method_not_allowed");
}

/** Browsers always send Origin on cross-site POSTs. Reject other sites posting to our forms. */
export function requireSameOrigin(req) {
  const origin = req.headers.get("origin");
  if (!origin) return; // curl, server-to-server, same-origin GETs
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || new URL(req.url).host;
  let originHost = "";
  try { originHost = new URL(origin).host; } catch { throw new HttpError(403, "forbidden"); }
  if (originHost !== host) throw new HttpError(403, "forbidden");
}

export async function readJson(req, maxChars = 20000) {
  const text = await req.text();
  if (text.length > maxChars) throw new HttpError(413, "too_large");
  try { return text ? JSON.parse(text) : {}; } catch { throw new HttpError(400, "bad_json"); }
}

export const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const isEmail = (v) => typeof v === "string" && v.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim());

/** Trim, strip control characters, cap length. */
export const clean = (v, max = 500) =>
  String(v ?? "").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "").trim().slice(0, max);

export function clientIp(req) {
  return (
    req.headers.get("x-nf-client-connection-ip") ||
    (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() ||
    "unknown"
  );
}

// Best-effort limiter (per warm function instance). Stops casual abuse; real protection is the email provider's limits.
const buckets = new Map();
export function rateLimit(key, limit, windowMs) {
  const now = Date.now();
  const hits = (buckets.get(key) || []).filter((t) => now - t < windowMs);
  if (hits.length >= limit) {
    buckets.set(key, hits);
    throw new HttpError(429, "too_many_requests");
  }
  hits.push(now);
  buckets.set(key, hits);
  if (buckets.size > 5000) buckets.clear();
}
export const _resetRateLimits = () => buckets.clear();

export const validation = (fields) => new HttpError(422, "validation", { fields });
