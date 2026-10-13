// Central place for settings read from environment variables (set in Netlify > Site configuration > Environment variables).
export const env = (key, fallback = "") => String(process.env[key] ?? fallback).trim();

export const GUIDES = {
  blueprint: { title: "The Home Shred Blueprint", file: "guides/home-shred-blueprint.pdf" },
  abs: { title: "28-Day Home Abs Challenge", file: "guides/28-day-home-abs.pdf" },
  shopping: { title: "The UK Cutting Shopping List", file: "guides/cutting-shopping-list.pdf" },
  kickstart: { title: "3-Day Fat Loss Kickstart", file: "guides/3-day-fat-loss-kickstart.pdf" },
  calories: { title: "How to Calculate Your Maintenance Calories", file: "guides/maintenance-calories-guide.pdf" },
};

export function siteUrl(req) {
  const configured = env("SITE_URL") || env("URL");
  const base = configured || (req ? new URL(req.url).origin : "http://localhost:8888");
  return base.replace(/\/+$/, "");
}

export const settings = () => ({
  from: env("MAIL_FROM", "Kye at Preski Fitness <onboarding@resend.dev>"),
  owner: env("OWNER_EMAIL"),
  supportEmail: env("SUPPORT_EMAIL") || env("OWNER_EMAIL"),
  planPricePence: Number.parseInt(env("PLAN_PRICE_PENCE", "3900"), 10) || 3900,
  coachingPrice: env("COACHING_PRICE", "£149 per month, 3-month minimum"),
  planDownloadUrl: env("PLAN_DOWNLOAD_URL"),
  chatModel: env("CHAT_MODEL", "claude-sonnet-5-5"),
});
