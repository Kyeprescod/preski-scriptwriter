// POST /api/apply -> emails the full coaching application to Kye and a receipt to the applicant.
import { settings, siteUrl } from "../lib/config.mjs";
import { addContact, applicantReceipt, ownerApplication, sendEmail } from "../lib/mail.mjs";
import { HttpError, clean, clientIp, handle, isEmail, json, rateLimit, readJson, requireMethod, requireSameOrigin, validation } from "../lib/http.mjs";

const QUESTIONS = {
  goal: "What do you want most?",
  why: "Why now? What's changed?",
  experience: "Training experience",
  equipment: "What equipment do you have at home?",
  days: "Days a week you can train",
  investment: "Are you ready to invest in coaching?",
  name: "First name",
  email: "Email",
};

export default handle(async (req) => {
  requireMethod(req, "POST");
  requireSameOrigin(req);
  rateLimit(`apply:${clientIp(req)}`, 5, 10 * 60 * 1000);

  const b = await readJson(req, 30000);
  if (clean(b.contact_me_by_fax_only)) return json(200, { ok: true });

  const a = {
    goal: clean(b.goal, 80), why: clean(b.why, 1500), experience: clean(b.experience, 80),
    equipment: clean(b.equipment, 300), days: clean(b.days, 40), stats: clean(b.stats, 120),
    blocker: clean(b.blocker, 1500), investment: clean(b.investment, 80), name: clean(b.name, 60),
    email: clean(b.email, 254).toLowerCase(), instagram: clean(b.instagram, 80), phone: clean(b.phone, 40),
  };
  const fields = {};
  for (const [k, label] of Object.entries(QUESTIONS)) if (!a[k]) fields[k] = `Please answer: ${label}`;
  if (a.email && !isEmail(a.email)) fields.email = "That email doesn't look right.";
  if (b.consent !== true) fields.consent = "Tick the box so I can contact you about coaching.";
  if (Object.keys(fields).length) throw validation(fields);

  const { owner } = settings();
  if (!owner) {
    console.error("OWNER_EMAIL is not set: applications cannot be delivered.");
    throw new HttpError(503, "owner_email_not_configured");
  }
  const base = siteUrl(req);

  // 1) The application itself is what matters: if this fails the visitor must see an error.
  const toOwner = ownerApplication(a);
  await sendEmail({ to: owner, subject: toOwner.subject, html: toOwner.html, text: toOwner.text, replyTo: a.email });

  // 2) Nice-to-haves: never fail the application because of these.
  try {
    const r = applicantReceipt({ firstName: a.name, siteBase: base });
    await sendEmail({ to: a.email, subject: r.subject, html: r.html, text: r.text, replyTo: owner });
  } catch (e) { console.error("Applicant receipt failed:", e && e.code ? e.code : e); }
  await addContact(a.email, a.name);

  return json(200, { ok: true });
});

export const config = { path: "/api/apply" };
