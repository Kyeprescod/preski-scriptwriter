// POST /api/subscribe  -> emails the chosen free guide to the visitor.
import { GUIDES, siteUrl } from "../lib/config.mjs";
import { addContact, guideEmail, sendEmail } from "../lib/mail.mjs";
import { clean, clientIp, handle, isEmail, json, rateLimit, readJson, requireMethod, requireSameOrigin, validation } from "../lib/http.mjs";

export default handle(async (req) => {
  requireMethod(req, "POST");
  requireSameOrigin(req);
  rateLimit(`sub:${clientIp(req)}`, 8, 10 * 60 * 1000);

  const b = await readJson(req);
  // Honeypot: a real person never sees this field. Pretend success so bots learn nothing.
  if (clean(b.contact_me_by_fax_only)) return json(200, { ok: true });

  const email = clean(b.email, 254).toLowerCase();
  const firstName = clean(b.first_name, 60);
  const guideKey = clean(b.guide, 20) || "blueprint";
  const fields = {};
  if (!firstName) fields.first_name = "Add your first name so I know who I'm talking to.";
  if (!isEmail(email)) fields.email = "That email doesn't look right. Check it and try again.";
  if (b.consent !== true) fields.consent = "Tick the box so I can email you the guide.";
  if (!GUIDES[guideKey]) fields.guide = "Choose one of the guides.";
  if (Object.keys(fields).length) throw validation(fields);

  const guide = GUIDES[guideKey];
  const base = siteUrl(req);
  const mail = guideEmail({ firstName, guide, url: `${base}/${guide.file}`, siteBase: base });
  await sendEmail({ to: email, subject: mail.subject, html: mail.html, text: mail.text }); // throws -> visitor sees a real error
  await addContact(email, firstName);
  return json(200, { ok: true, guide: guideKey });
});

export const config = { path: "/api/subscribe" };
