import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { _resetRateLimits } from "../netlify/lib/http.mjs";
import subscribe from "../netlify/functions/subscribe.mjs";
import apply from "../netlify/functions/apply.mjs";
import checkout from "../netlify/functions/checkout.mjs";
import webhook, { verifyStripeSignature } from "../netlify/functions/stripe-webhook.mjs";
import chat from "../netlify/functions/chat.mjs";
import health from "../netlify/functions/health.mjs";

const realFetch = globalThis.fetch;
let calls;           // every outgoing request our functions make
let responder;       // (url, init) -> Response, set per test

const ENV_KEYS = ["RESEND_API_KEY", "OWNER_EMAIL", "MAIL_FROM", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "PLAN_DOWNLOAD_URL",
  "PLAN_PAYMENT_LINK", "ANTHROPIC_API_KEY", "SITE_URL", "URL", "RESEND_AUDIENCE_ID", "PLAN_PRICE_PENCE"];
const savedEnv = {};

beforeEach(() => {
  for (const k of ENV_KEYS) { savedEnv[k] = process.env[k]; delete process.env[k]; }
  Object.assign(process.env, { SITE_URL: "https://preskifitness.com", RESEND_API_KEY: "re_test", OWNER_EMAIL: "kye@example.com" });
  _resetRateLimits();
  calls = [];
  responder = () => new Response(JSON.stringify({ id: "x" }), { status: 200 });
  globalThis.fetch = async (url, init = {}) => { calls.push({ url: String(url), init, body: init.body ? safeParse(init.body) : null }); return responder(String(url), init); };
});
afterEach(() => {
  globalThis.fetch = realFetch;
  for (const k of ENV_KEYS) { if (savedEnv[k] === undefined) delete process.env[k]; else process.env[k] = savedEnv[k]; }
});

function safeParse(b) { try { return JSON.parse(b); } catch { return typeof b === "string" ? b : String(b); } }
const post = (path, body, headers = {}) => new Request(`https://preskifitness.com${path}`, {
  method: "POST", headers: { "content-type": "application/json", host: "preskifitness.com", ...headers }, body: typeof body === "string" ? body : JSON.stringify(body) });
const emails = () => calls.filter((c) => c.url === "https://api.resend.com/emails");

/* ---------------- free guide ---------------- */
test("subscribe: sends the chosen guide with a working link", async () => {
  const res = await subscribe(post("/api/subscribe", { email: "Jo@Example.com", first_name: "Jo", guide: "abs", consent: true }));
  assert.equal(res.status, 200);
  assert.equal(emails().length, 1);
  const m = emails()[0].body;
  assert.deepEqual(m.to, ["jo@example.com"]);
  assert.match(m.subject, /28-Day Home Abs/);
  assert.match(m.html, /https:\/\/preskifitness\.com\/guides\/28-day-home-abs\.pdf/);
  assert.equal(emails()[0].init.headers.Authorization, "Bearer re_test");
});

test("subscribe: tells the visitor exactly what is missing (422)", async () => {
  const res = await subscribe(post("/api/subscribe", { email: "nope", first_name: "", guide: "blueprint", consent: false }));
  const data = await res.json();
  assert.equal(res.status, 422);
  assert.deepEqual(Object.keys(data.fields).sort(), ["consent", "email", "first_name"]);
  assert.equal(emails().length, 0);
});

test("subscribe: honeypot fools bots but sends nothing", async () => {
  const res = await subscribe(post("/api/subscribe", { email: "bot@example.com", first_name: "Bot", consent: true, contact_me_by_fax_only: "http://spam" }));
  assert.equal(res.status, 200);
  assert.equal(emails().length, 0);
});

test("subscribe: if email fails the visitor sees an error, never a fake success", async () => {
  responder = () => new Response("nope", { status: 500 });
  const res = await subscribe(post("/api/subscribe", { email: "a@b.co", first_name: "A", guide: "blueprint", consent: true }));
  assert.equal(res.status, 502);
  assert.equal((await res.json()).error, "email_failed");
});

test("subscribe: not configured -> 503, not success", async () => {
  delete process.env.RESEND_API_KEY;
  const res = await subscribe(post("/api/subscribe", { email: "a@b.co", first_name: "A", guide: "blueprint", consent: true }));
  assert.equal(res.status, 503);
});

test("subscribe: other websites cannot post to it (403) and spam is rate limited (429)", async () => {
  const bad = await subscribe(post("/api/subscribe", { email: "a@b.co", first_name: "A", consent: true }, { origin: "https://evil.example" }));
  assert.equal(bad.status, 403);
  let last;
  for (let i = 0; i < 9; i++) last = await subscribe(post("/api/subscribe", { email: `a${i}@b.co`, first_name: "A", guide: "blueprint", consent: true }));
  assert.equal(last.status, 429);
});

test("subscribe: adds to the subscriber list when one is configured", async () => {
  process.env.RESEND_AUDIENCE_ID = "aud_1";
  await subscribe(post("/api/subscribe", { email: "a@b.co", first_name: "A", guide: "blueprint", consent: true }));
  assert.ok(calls.some((c) => c.url.endsWith("/audiences/aud_1/contacts")));
});

/* ---------------- coaching application ---------------- */
const goodApp = { goal: "Lose fat", why: "Holiday in June", experience: "Complete beginner", equipment: "Dumbbells", days: "4",
  investment: "Yes, ready to start", name: "Sam", email: "sam@example.com", instagram: "@sam", consent: true };

test("apply: Kye gets every answer, applicant gets a receipt", async () => {
  const res = await apply(post("/api/apply", goodApp));
  assert.equal(res.status, 200);
  const [toKye, toSam] = emails();
  assert.deepEqual(toKye.body.to, ["kye@example.com"]);
  assert.equal(toKye.body.reply_to, "sam@example.com");
  assert.match(toKye.body.subject, /Sam.*Lose fat/);
  assert.match(toKye.body.html, /Holiday in June/);
  assert.deepEqual(toSam.body.to, ["sam@example.com"]);
});

test("apply: names every unanswered question", async () => {
  const res = await apply(post("/api/apply", { ...goodApp, why: "", experience: "", consent: false }));
  const data = await res.json();
  assert.equal(res.status, 422);
  assert.deepEqual(Object.keys(data.fields).sort(), ["consent", "experience", "why"]);
  assert.match(data.fields.why, /Why now/);
  assert.equal(emails().length, 0);
});

test("apply: cannot silently lose applications when owner email is missing", async () => {
  delete process.env.OWNER_EMAIL;
  const res = await apply(post("/api/apply", goodApp));
  assert.equal(res.status, 503);
});

test("apply: receipt failure does not fail the application", async () => {
  let n = 0;
  responder = () => (++n === 2 ? new Response("x", { status: 500 }) : new Response("{}", { status: 200 }));
  const res = await apply(post("/api/apply", goodApp));
  assert.equal(res.status, 200);
});

test("apply: HTML in answers is escaped in the email", async () => {
  await apply(post("/api/apply", { ...goodApp, why: "<script>alert(1)</script>" }));
  assert.ok(!emails()[0].body.html.includes("<script>alert(1)"));
  assert.match(emails()[0].body.html, /&lt;script&gt;/);
});

/* ---------------- checkout ---------------- */
test("checkout: not configured -> 503 (button shows a helpful message)", async () => {
  const res = await checkout(post("/api/checkout", {}));
  assert.equal(res.status, 503);
});

test("checkout: payment link mode just returns the link", async () => {
  process.env.PLAN_PAYMENT_LINK = "https://buy.stripe.com/abc";
  const res = await checkout(post("/api/checkout", {}));
  assert.equal((await res.json()).url, "https://buy.stripe.com/abc");
});

test("checkout: creates a £39 GBP Stripe session with success and cancel pages", async () => {
  process.env.STRIPE_SECRET_KEY = "sk_test_x";
  responder = () => new Response(JSON.stringify({ url: "https://checkout.stripe.com/c/pay/cs_1" }), { status: 200 });
  const res = await checkout(post("/api/checkout", {}));
  assert.equal((await res.json()).url, "https://checkout.stripe.com/c/pay/cs_1");
  const p = new URLSearchParams(String(calls[0].init.body));
  assert.equal(p.get("line_items[0][price_data][unit_amount]"), "3900");
  assert.equal(p.get("line_items[0][price_data][currency]"), "gbp");
  assert.equal(p.get("metadata[product]"), "plan");
  assert.match(p.get("success_url"), /thanks\.html\?type=plan/);
  assert.equal(p.get("cancel_url"), "https://preskifitness.com/plan.html");
  assert.equal(calls[0].init.headers.Authorization, "Bearer sk_test_x");
});

test("checkout: Stripe failure -> 502", async () => {
  process.env.STRIPE_SECRET_KEY = "sk_test_x";
  responder = () => new Response(JSON.stringify({ error: { message: "bad" } }), { status: 400 });
  assert.equal((await checkout(post("/api/checkout", {}))).status, 502);
});

/* ---------------- plan delivery (Stripe webhook) ---------------- */
const SECRET = "whsec_test";
function signed(event, { secret = SECRET, t = Math.floor(Date.now() / 1000) } = {}) {
  const raw = JSON.stringify(event);
  const v1 = createHmac("sha256", secret).update(`${t}.${raw}`).digest("hex");
  return new Request("https://preskifitness.com/api/stripe-webhook", { method: "POST", headers: { "stripe-signature": `t=${t},v1=${v1}`, host: "preskifitness.com" }, body: raw });
}
const paid = (over = {}) => ({ id: "evt_1", type: "checkout.session.completed", data: { object: {
  payment_status: "paid", amount_total: 3900, metadata: { product: "plan" }, customer_details: { email: "buyer@example.com", name: "Alex Jones" }, ...over } } });

test("webhook: rejects forged and stale requests", async () => {
  process.env.STRIPE_WEBHOOK_SECRET = SECRET;
  assert.equal((await webhook(signed(paid(), { secret: "whsec_wrong" }))).status, 400);
  assert.equal((await webhook(signed(paid(), { t: Math.floor(Date.now() / 1000) - 3600 }))).status, 400);
  const noHeader = new Request("https://preskifitness.com/api/stripe-webhook", { method: "POST", body: "{}" });
  assert.equal((await webhook(noHeader)).status, 400);
  assert.equal(emails().length, 0);
  assert.equal(verifyStripeSignature("{}", "t=1,v1=zz", SECRET), false);
});

test("webhook: a paid order emails the programme link to the customer and alerts Kye", async () => {
  Object.assign(process.env, { STRIPE_WEBHOOK_SECRET: SECRET, PLAN_DOWNLOAD_URL: "https://files.example.com/plan.pdf" });
  const res = await webhook(signed(paid()));
  assert.equal(res.status, 200);
  const [toCustomer, toKye] = emails();
  assert.deepEqual(toCustomer.body.to, ["buyer@example.com"]);
  assert.match(toCustomer.body.html, /files\.example\.com\/plan\.pdf/);
  assert.equal(toCustomer.init.headers["Idempotency-Key"], "plan-evt_1");
  assert.deepEqual(toKye.body.to, ["kye@example.com"]);
  assert.match(toKye.body.subject, /New sale/);
});

test("webhook: money taken but no plan file configured -> customer told, Kye alerted loudly", async () => {
  process.env.STRIPE_WEBHOOK_SECRET = SECRET;
  const res = await webhook(signed(paid()));
  assert.equal(res.status, 200);
  const [toCustomer, toKye] = emails();
  assert.match(toCustomer.body.subject, /Payment received/);
  assert.match(toKye.body.subject, /ACTION NEEDED/);
});

test("webhook: if email fails Stripe gets an error so it retries later", async () => {
  Object.assign(process.env, { STRIPE_WEBHOOK_SECRET: SECRET, PLAN_DOWNLOAD_URL: "https://x.test/p.pdf" });
  responder = () => new Response("down", { status: 500 });
  assert.equal((await webhook(signed(paid()))).status, 502);
});

test("webhook: unpaid, other products and other event types are ignored safely", async () => {
  process.env.STRIPE_WEBHOOK_SECRET = SECRET;
  assert.equal((await (await webhook(signed(paid({ payment_status: "unpaid" })))).json()).ignored, "not_paid_yet");
  assert.equal((await (await webhook(signed(paid({ metadata: { product: "coaching" } })))).json()).ignored, "other_product");
  assert.equal((await (await webhook(signed({ id: "e2", type: "charge.refunded", data: { object: {} } }))).json()).ignored, "charge.refunded");
  assert.equal(emails().length, 0);
});

/* ---------------- chat ---------------- */
test("chat: not configured -> 503 so the page uses its built-in answers", async () => {
  assert.equal((await chat(post("/api/chat", { messages: [{ role: "user", content: "hi" }] }))).status, 503);
});

test("chat: drops the leading greeting, merges turns, returns Claude's reply", async () => {
  process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  responder = () => new Response(JSON.stringify({ content: [{ type: "text", text: "Coaching is £149." }] }), { status: 200 });
  const res = await chat(post("/api/chat", { messages: [
    { role: "assistant", content: "Alright, I'm the Preski assistant." },
    { role: "user", content: "How much?" }, { role: "user", content: "for coaching" }] }));
  assert.equal((await res.json()).reply, "Coaching is £149.");
  const sent = calls[0].body;
  assert.equal(sent.messages.length, 1);
  assert.equal(sent.messages[0].role, "user");
  assert.match(sent.messages[0].content, /How much\?\nfor coaching/);
  assert.match(sent.system, /Never give medical advice/);
  assert.equal(calls[0].init.headers["x-api-key"], "sk-ant-test");
});

test("chat: provider failure -> 502 (page falls back)", async () => {
  process.env.ANTHROPIC_API_KEY = "k";
  responder = () => new Response("{}", { status: 500 });
  assert.equal((await chat(post("/api/chat", { messages: [{ role: "user", content: "hi" }] }))).status, 502);
});

/* ---------------- setup status ---------------- */
test("health: reports what is connected without leaking secrets", async () => {
  process.env.STRIPE_SECRET_KEY = "sk_live_SUPERSECRET";
  const res = await health(new Request("https://preskifitness.com/api/health"));
  const text = await res.text();
  assert.ok(!text.includes("SUPERSECRET") && !text.includes("re_test"));
  const data = JSON.parse(text);
  assert.equal(data.ok, false);
  assert.ok(data.missing.includes("planDelivery") && data.missing.includes("stripeWebhook"));
  assert.equal(data.services.email, true);
});
