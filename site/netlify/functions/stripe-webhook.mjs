// POST /api/stripe-webhook -> Stripe tells us a payment succeeded; we email the programme to the customer.
// Stripe retries failed deliveries for days, and every email uses an idempotency key, so the customer never gets duplicates.
import { createHmac, timingSafeEqual } from "node:crypto";
import { env, settings, siteUrl } from "../lib/config.mjs";
import { ownerAlert, planEmail, planPendingEmail, sendEmail } from "../lib/mail.mjs";
import { HttpError, handle, json, requireMethod } from "../lib/http.mjs";

export function verifyStripeSignature(rawBody, header, secret, nowMs = Date.now(), toleranceSec = 300) {
  if (!header || !secret) return false;
  const parts = header.split(",").map((s) => s.trim().split("="));
  const t = parts.find(([k]) => k === "t")?.[1];
  const sigs = parts.filter(([k]) => k === "v1").map(([, v]) => v);
  if (!t || !sigs.length || Math.abs(nowMs / 1000 - Number(t)) > toleranceSec) return false;
  const expected = createHmac("sha256", secret).update(`${t}.${rawBody}`).digest();
  return sigs.some((s) => {
    const got = Buffer.from(s, "hex");
    return got.length === expected.length && timingSafeEqual(got, expected);
  });
}

export default handle(async (req) => {
  requireMethod(req, "POST");
  const secret = env("STRIPE_WEBHOOK_SECRET");
  if (!secret) throw new HttpError(503, "webhook_not_configured");
  const raw = await req.text(); // the exact bytes Stripe signed
  if (!verifyStripeSignature(raw, req.headers.get("stripe-signature"), secret)) throw new HttpError(400, "bad_signature");

  const event = JSON.parse(raw);
  const okTypes = ["checkout.session.completed", "checkout.session.async_payment_succeeded"];
  if (!okTypes.includes(event.type)) return json(200, { ignored: event.type });
  const s = event.data?.object || {};
  if (s.payment_status !== "paid") return json(200, { ignored: "not_paid_yet" });
  if (s.metadata?.product && s.metadata.product !== "plan") return json(200, { ignored: "other_product" });

  const email = s.customer_details?.email || s.customer_email;
  const firstName = (s.customer_details?.name || "").split(" ")[0] || "";
  const { planDownloadUrl, owner, supportEmail } = settings();
  const base = siteUrl(req);
  if (!email) throw new HttpError(500, "no_customer_email");

  if (planDownloadUrl) {
    const m = planEmail({ firstName, url: planDownloadUrl, siteBase: base });
    await sendEmail({ to: email, subject: m.subject, html: m.html, text: m.text, replyTo: owner || undefined, idempotencyKey: `plan-${event.id}` });
  } else {
    // We must never take money and say nothing: tell the customer, and shout at the owner.
    const m = planPendingEmail({ firstName, support: supportEmail });
    await sendEmail({ to: email, subject: m.subject, html: m.html, text: m.text, replyTo: owner || undefined, idempotencyKey: `plan-${event.id}` });
  }
  if (owner) {
    const amount = ((s.amount_total || 0) / 100).toFixed(2);
    const lines = planDownloadUrl
      ? [`${firstName || "A customer"} (${email}) bought the 8-Week Home Shred Programme for £${amount}.`, "Their programme was emailed automatically."]
      : [`${firstName || "A customer"} (${email}) paid £${amount} but PLAN_DOWNLOAD_URL is not set, so they were NOT sent the programme.`, "Send it to them manually today and add PLAN_DOWNLOAD_URL in Netlify settings."];
    const a = ownerAlert({ subject: planDownloadUrl ? "New sale: 8-Week programme" : "ACTION NEEDED: send the programme manually", lines });
    try { await sendEmail({ to: owner, subject: a.subject, html: a.html, text: a.text, idempotencyKey: `owner-${event.id}` }); }
    catch (e) { console.error("Owner sale alert failed:", e && e.code ? e.code : e); }
  }
  return json(200, { ok: true });
});

export const config = { path: "/api/stripe-webhook" };
