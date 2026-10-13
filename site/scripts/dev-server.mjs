// Local development server:  npm run dev   ->  http://localhost:8888
// Serves the site and runs the same functions Netlify runs. Put real keys in a file called .env to test with real services,
// or run with DEV_MOCK=1 to use fake email/Stripe/Claude (used by the automated browser tests).
import http from "node:http";
import { readFile, readdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.env.PORT || 8888);
const MOCK = process.env.DEV_MOCK === "1";

if (existsSync(path.join(root, ".env"))) {
  for (const line of readFileSync(path.join(root, ".env"), "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m && !line.trim().startsWith("#") && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

/* ---------- mock external services (DEV_MOCK=1) ---------- */
const outbox = [];
const MOCK_ENV = { RESEND_API_KEY: "re_mock", OWNER_EMAIL: "kye@example.com", STRIPE_SECRET_KEY: "sk_mock", STRIPE_WEBHOOK_SECRET: "whsec_mock", PLAN_DOWNLOAD_URL: "https://files.example.com/plan.pdf" };
let mode = "ok";
function applyMode(m) {
  mode = m;
  for (const k of Object.keys(MOCK_ENV)) delete process.env[k];
  delete process.env.ANTHROPIC_API_KEY;
  if (m === "unconfigured") return;
  Object.assign(process.env, MOCK_ENV);
  if (m === "chat") process.env.ANTHROPIC_API_KEY = "sk-ant-mock";
}
if (MOCK) {
  applyMode("ok");
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url);
    if (!/^https:\/\/api\.(resend\.com|stripe\.com|anthropic\.com)/.test(u)) return realFetch(url, init);
    let body = init.body; if (body instanceof URLSearchParams) body = body.toString(); else { try { body = JSON.parse(init.body); } catch {} }
    outbox.push({ url: u, body });
    if (mode === "email_down" && u.includes("resend.com")) return new Response("down", { status: 500 });
    if (u.includes("stripe.com")) return new Response(JSON.stringify({ url: "https://checkout.stripe.com/c/pay/cs_mock" }), { status: 200 });
    if (u.includes("anthropic.com")) return new Response(JSON.stringify({ content: [{ type: "text", text: "Mock assistant reply." }] }), { status: 200 });
    return new Response(JSON.stringify({ id: "mock" }), { status: 200 });
  };
}

/* ---------- load functions and their routes ---------- */
const routes = new Map();
for (const f of (await readdir(path.join(root, "netlify/functions"))).filter((n) => n.endsWith(".mjs"))) {
  const mod = await import(pathToFileURL(path.join(root, "netlify/functions", f)).href);
  if (mod.config?.path) routes.set(mod.config.path, mod.default);
}

const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf", ".svg": "image/svg+xml", ".ico": "image/x-icon" };

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (MOCK && url.pathname === "/__outbox") {
      if (req.method === "DELETE") { outbox.length = 0; res.end("cleared"); return; }
      res.setHeader("content-type", "application/json"); res.end(JSON.stringify(outbox)); return;
    }
    if (MOCK && url.pathname === "/__mode") { applyMode(url.searchParams.get("m") || "ok"); res.end(mode); return; }
    const handler = routes.get(url.pathname);
    if (handler) {
      const chunks = []; for await (const c of req) chunks.push(c);
      const request = new Request(url, { method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.concat(chunks) });
      const out = await handler(request, {});
      res.writeHead(out.status, Object.fromEntries(out.headers));
      res.end(Buffer.from(await out.arrayBuffer()));
      return;
    }
    let file = path.join(root, decodeURIComponent(url.pathname));
    if (!file.startsWith(root) || /[\\/](netlify|test|scripts|node_modules)[\\/]|package\.json|netlify\.toml|\.env/.test(file.slice(root.length))) { res.writeHead(404); res.end("Not found"); return; }
    if (file.endsWith(path.sep) || !path.extname(file)) file = path.join(file, "index.html");
    const data = await readFile(file);
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch (e) {
    if (e.code === "ENOENT") { res.writeHead(404); res.end("Not found"); } else { console.error(e); res.writeHead(500); res.end("Server error"); }
  }
}).listen(PORT, () => console.log(`Preski site running at http://localhost:${PORT}${MOCK ? "  (mock services)" : ""}`));
