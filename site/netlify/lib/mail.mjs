// Email sending through Resend (https://resend.com). One place for the API call and every email template.
import { env, settings } from "./config.mjs";
import { HttpError, escapeHtml } from "./http.mjs";

const NAVY = "#071A3D";
const RED = "#E8323C";

export async function sendEmail({ to, subject, html, text, replyTo, idempotencyKey }) {
  const key = env("RESEND_API_KEY");
  if (!key) throw new HttpError(503, "email_not_configured");
  const { from } = settings();
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "content-type": "application/json",
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify({ from, to: Array.isArray(to) ? to : [to], subject, html, text, ...(replyTo ? { reply_to: replyTo } : {}) }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.error("Resend rejected the email:", res.status, detail.slice(0, 400));
    throw new HttpError(502, "email_failed");
  }
  return res.json().catch(() => ({}));
}

/** Optional: keep a list of subscribers in a Resend Audience so Kye can send broadcasts later. Never blocks the user. */
export async function addContact(email, firstName) {
  const key = env("RESEND_API_KEY");
  const audience = env("RESEND_AUDIENCE_ID");
  if (!key || !audience) return false;
  try {
    const res = await fetch(`https://api.resend.com/audiences/${audience}/contacts`, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "content-type": "application/json" },
      body: JSON.stringify({ email, first_name: firstName || undefined, unsubscribed: false }),
    });
    return res.ok;
  } catch (e) {
    console.error("Could not add contact:", e);
    return false;
  }
}

function layout({ preheader, heading, bodyHtml, button, footer }) {
  return `<!doctype html><html lang="en-GB"><body style="margin:0;background:#EDF1F7;font-family:Arial,Helvetica,sans-serif;color:#0A1631">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">${escapeHtml(preheader || "")}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EDF1F7"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:8px;overflow:hidden">
<tr><td style="background:${NAVY};padding:20px 28px;font-size:22px;font-weight:800;letter-spacing:1px;color:#ffffff">PRESKI<span style="color:${RED}">FITNESS</span></td></tr>
<tr><td style="padding:28px">
<h1 style="margin:0 0 14px;font-size:24px;line-height:1.2;color:${NAVY}">${escapeHtml(heading)}</h1>
${bodyHtml}
${button ? `<p style="margin:26px 0"><a href="${escapeHtml(button.url)}" style="background:${RED};color:#ffffff;text-decoration:none;font-weight:700;padding:14px 26px;border-radius:6px;display:inline-block">${escapeHtml(button.label)}</a></p><p style="font-size:13px;color:#3B4A68;margin:0">Button not working? Copy this link into your browser:<br><span style="word-break:break-all">${escapeHtml(button.url)}</span></p>` : ""}
</td></tr>
<tr><td style="padding:18px 28px;background:#F6F8FB;font-size:12px;color:#3B4A68;line-height:1.5">${footer || "Preski Fitness · Get in shape and get shredded at home."}</td></tr>
</table></td></tr></table></body></html>`;
}
const p = (t) => `<p style="margin:0 0 14px;font-size:16px;line-height:1.55">${t}</p>`;

export function guideEmail({ firstName, guide, url, siteBase }) {
  const hi = firstName ? `Hi ${escapeHtml(firstName)},` : "Hi,";
  return {
    subject: `Your free guide: ${guide.title}`,
    html: layout({
      preheader: "Your download link is inside.",
      heading: "Your guide is here",
      bodyHtml: p(hi) + p(`Here's <strong>${escapeHtml(guide.title)}</strong>, as promised. Open it on your phone or save it to your device.`) +
        p(`If you want me to build the plan around you, <a href="${escapeHtml(siteBase)}/apply.html" style="color:${RED}">apply for coaching here</a>. I read every application myself.`) + p("Kye"),
      button: { label: "Download the guide", url },
      footer: "You asked for this guide on preskifitness.com. If that wasn't you, ignore this email and nothing else will happen.",
    }),
    text: `${hi}\n\nHere's ${guide.title}: ${url}\n\nWant a plan built around you? Apply for coaching: ${siteBase}/apply.html\n\nKye`,
  };
}

export function applicantReceipt({ firstName, siteBase }) {
  return {
    subject: "Got your application. I'll reply within 48 hours",
    html: layout({
      preheader: "Application received.",
      heading: "Application received",
      bodyHtml: p(`Hi ${escapeHtml(firstName)},`) +
        p("Thanks for applying. I read every application myself and I'll reply by email or DM within 48 hours.") +
        p(`While you wait, grab the free 3-Day Fat Loss Kickstart so you can start today: <a href="${escapeHtml(siteBase)}/guides/3-day-fat-loss-kickstart.pdf" style="color:${RED}">download it here</a>.`) + p("Kye"),
    }),
    text: `Hi ${firstName},\n\nThanks for applying. I'll reply within 48 hours.\n\nFree 3-Day Kickstart: ${siteBase}/guides/3-day-fat-loss-kickstart.pdf\n\nKye`,
  };
}

const LABELS = {
  goal: "Goal", why: "Why now", experience: "Experience", equipment: "Equipment", days: "Days a week",
  stats: "Age / height / weight", blocker: "What's stopped them", investment: "Ready to invest",
  name: "Name", email: "Email", instagram: "Instagram / TikTok", phone: "WhatsApp",
};

export function ownerApplication(a) {
  const rows = Object.keys(LABELS)
    .map((k) => `<tr><td style="padding:8px 10px;border-bottom:1px solid #e3e8f1;font-weight:700;vertical-align:top;white-space:nowrap">${LABELS[k]}</td><td style="padding:8px 10px;border-bottom:1px solid #e3e8f1">${escapeHtml(a[k] || "-").replace(/\n/g, "<br>")}</td></tr>`)
    .join("");
  return {
    subject: `New coaching application: ${a.name} (${a.goal})`,
    html: layout({
      preheader: `${a.name} wants to start: ${a.investment}`,
      heading: `New application: ${a.name}`,
      bodyHtml: `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:15px;border-collapse:collapse">${rows}</table>` +
        p(`<br>Reply to this email to answer ${escapeHtml(a.name)} directly.`),
      footer: "Sent automatically by your website.",
    }),
    text: Object.keys(LABELS).map((k) => `${LABELS[k]}: ${a[k] || "-"}`).join("\n"),
  };
}

export function planEmail({ firstName, url, siteBase }) {
  const hi = firstName ? `Hi ${escapeHtml(firstName)},` : "Hi,";
  return {
    subject: "Your 8-Week Home Shred Programme",
    html: layout({
      preheader: "Payment confirmed. Your programme is inside.",
      heading: "Week 1 starts now",
      bodyHtml: p(hi) + p("Thank you. Your payment went through and your <strong>8-Week Home Shred Programme</strong> is ready.") +
        p("Before Day 1: take your \"before\" photos and weigh in tomorrow morning. Then start your first session.") +
        p(`If you'd like me to coach you through it, <a href="${escapeHtml(siteBase)}/apply.html" style="color:${RED}">apply here</a>.`) + p("Kye"),
      button: { label: "Open your programme", url },
      footer: "You bought this on preskifitness.com. Stripe has emailed your receipt separately.",
    }),
    text: `${hi}\n\nYour 8-Week Home Shred Programme: ${url}\n\nKye`,
  };
}

export function planPendingEmail({ firstName, support }) {
  const hi = firstName ? `Hi ${escapeHtml(firstName)},` : "Hi,";
  return {
    subject: "Payment received. Your programme is on its way",
    html: layout({
      preheader: "Payment received.",
      heading: "Payment received",
      bodyHtml: p(hi) + p("Thank you. Your payment went through. I'm sending your programme to you personally and you'll have it within 24 hours.") +
        p(`Any problem, reply to this email${support ? ` or write to ${escapeHtml(support)}` : ""}.`) + p("Kye"),
    }),
    text: `${hi}\n\nPayment received. You'll have your programme within 24 hours. Reply to this email if there's a problem.\n\nKye`,
  };
}

export function ownerAlert({ subject, lines }) {
  return {
    subject,
    html: layout({ preheader: subject, heading: subject, bodyHtml: lines.map((l) => p(escapeHtml(l))).join(""), footer: "Sent automatically by your website." }),
    text: lines.join("\n"),
  };
}
