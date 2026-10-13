// GET /api/health -> shows which settings are connected (true/false only, never the secrets).
import { env, settings, siteUrl } from "../lib/config.mjs";
import { handle, json } from "../lib/http.mjs";

export default handle(async (req) => {
  const s = settings();
  const services = {
    email: !!env("RESEND_API_KEY"),
    ownerEmail: !!s.owner,
    checkout: !!(env("STRIPE_SECRET_KEY") || env("PLAN_PAYMENT_LINK")),
    stripeWebhook: !!env("STRIPE_WEBHOOK_SECRET"),
    planDelivery: !!s.planDownloadUrl,
    chatAssistant: !!env("ANTHROPIC_API_KEY"),
    subscriberList: !!env("RESEND_AUDIENCE_ID"),
    customSenderAddress: !/onboarding@resend\.dev/.test(s.from),
  };
  const needed = ["email", "ownerEmail", "checkout", "stripeWebhook", "planDelivery"];
  return json(200, {
    ok: needed.every((k) => services[k]),
    missing: needed.filter((k) => !services[k]),
    services,
    siteUrl: siteUrl(req),
  });
});

export const config = { path: "/api/health" };
