// POST /api/checkout -> creates a Stripe Checkout session for the 8-week programme and returns its URL.
import { env, settings, siteUrl } from "../lib/config.mjs";
import { HttpError, clientIp, handle, json, rateLimit, requireMethod, requireSameOrigin } from "../lib/http.mjs";

export default handle(async (req) => {
  requireMethod(req, "POST");
  requireSameOrigin(req);
  rateLimit(`co:${clientIp(req)}`, 10, 10 * 60 * 1000);

  // Simplest option: a Stripe Payment Link pasted into settings.
  const link = env("PLAN_PAYMENT_LINK");
  const secret = env("STRIPE_SECRET_KEY");
  if (!secret && link) return json(200, { url: link });
  if (!secret) throw new HttpError(503, "checkout_not_configured");

  const base = siteUrl(req);
  const form = new URLSearchParams({
    mode: "payment",
    "line_items[0][quantity]": "1",
    "line_items[0][price_data][currency]": "gbp",
    "line_items[0][price_data][unit_amount]": String(settings().planPricePence),
    "line_items[0][price_data][product_data][name]": "8-Week Home Shred Programme",
    "line_items[0][price_data][product_data][description]": "Self-guided 8-week home training programme by Kye Prescod",
    "metadata[product]": "plan",
    "payment_intent_data[metadata][product]": "plan",
    success_url: `${base}/thanks.html?type=plan&session_id={CHECKOUT_SESSION_ID}#plan`,
    cancel_url: `${base}/plan.html`,
    billing_address_collection: "auto",
    allow_promotion_codes: "true",
  });
  const res = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: { Authorization: `Bearer ${secret}`, "content-type": "application/x-www-form-urlencoded" },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.url) {
    console.error("Stripe checkout session failed:", res.status, JSON.stringify(data).slice(0, 400));
    throw new HttpError(502, "checkout_failed");
  }
  return json(200, { url: data.url });
});

export const config = { path: "/api/checkout" };
