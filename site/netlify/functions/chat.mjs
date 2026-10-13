// POST /api/chat -> the "Ask Preski" assistant, powered by Claude. If no key is set the site falls back to built-in answers.
import { env, settings } from "../lib/config.mjs";
import { HttpError, clean, clientIp, handle, json, rateLimit, readJson, requireMethod, requireSameOrigin } from "../lib/http.mjs";

const SYSTEM = (price) => `You are the website assistant for Preski Fitness, run by Kye Prescod (Level 2 Gym Instructor, "King Shredder"). Preski Fitness helps people get in shape and get shredded at home with no gym.

Voice: British English, direct, practical, friendly, plain words. No hype, no fake motivation, no emojis, no long intros. Keep replies under 90 words.

What you can talk about:
- Free guides (Home Shred Blueprint, 28-Day Home Abs, Cutting Shopping List, 3-Day Kickstart): tell people to pick one in the "Free guides" section on the home page.
- 1:1 online coaching: ${price}. Application only; Kye reads every application and replies within 48 hours. Link: apply.html
- 8-Week Home Shred Programme: self-guided, 4 sessions a week of 25-45 minutes, dumbbell and bodyweight versions. Link: plan.html
- General home training and fat loss basics: protein roughly 1.6-2.2 g per kg bodyweight, a small calorie deficit, walking daily, progressive overload.

Rules you must follow:
- Never give medical advice, diagnose anything, or promise results. For injuries or health conditions say to check with their GP.
- Never invent policies, prices, discounts or refund terms. If asked about refunds, cancellation or anything you aren't sure of, say Kye will confirm it before they pay anything.
- If you don't know, say so and point to the coaching application or DM "COACH" on Instagram.
- Stay on topic. Politely decline unrelated requests.
- You may link pages using markdown like [Apply for coaching](apply.html).`;

function normalise(messages) {
  const out = [];
  for (const m of Array.isArray(messages) ? messages.slice(-12) : []) {
    const role = m && m.role === "assistant" ? "assistant" : m && m.role === "user" ? "user" : null;
    const content = clean(m && m.content, 600);
    if (!role || !content) continue;
    if (!out.length && role !== "user") continue; // the API needs the first message to be from the user
    if (out.length && out[out.length - 1].role === role) out[out.length - 1].content += "\n" + content;
    else out.push({ role, content });
  }
  return out;
}

export default handle(async (req) => {
  requireMethod(req, "POST");
  requireSameOrigin(req);
  rateLimit(`chat:${clientIp(req)}`, 20, 10 * 60 * 1000);
  const key = env("ANTHROPIC_API_KEY");
  if (!key) throw new HttpError(503, "chat_not_configured");

  const b = await readJson(req, 12000);
  const messages = normalise(b.messages);
  if (!messages.length || messages[messages.length - 1].role !== "user") throw new HttpError(422, "no_question");

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  let res;
  try {
    res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      signal: ctrl.signal,
      headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model: settings().chatModel, max_tokens: 300, system: SYSTEM(settings().coachingPrice), messages }),
    });
  } catch (e) {
    console.error("Chat request failed:", e && e.name);
    throw new HttpError(502, "chat_failed");
  } finally { clearTimeout(timer); }
  const data = await res.json().catch(() => ({}));
  const reply = (data.content || []).filter((c) => c.type === "text").map((c) => c.text).join("\n").trim();
  if (!res.ok || !reply) {
    console.error("Anthropic error:", res.status, JSON.stringify(data).slice(0, 300));
    throw new HttpError(502, "chat_failed");
  }
  return json(200, { reply });
});

export const config = { path: "/api/chat" };
