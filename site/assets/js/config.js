/* ============================================================
   PRESKI FITNESS: SITE SETTINGS (shown on the page)
   Prices here are what visitors SEE. The price actually charged at checkout
   is set on the server (PLAN_PRICE_PENCE in Netlify, default 3900 = £39), so keep them in step.
   Secrets (API keys) never go in this file: they live in Netlify's environment settings.
   ============================================================ */
window.PRESKI_CONFIG = {
  // Shown on the thank-you and privacy pages. Use the address you actually read.
  contactEmail: "hello@preskifitness.com",

  prices: {
    coachingMonthly: "£149",
    coachingNote: "per month · 3-month minimum",
    plan: "£39",
    planNote: "one-off · lifetime access"
  },

  // Optional booking link for the coaching call (Calendly / Cal.com). Leave "" to hide the button.
  bookingUrl: "",

  // Social links (check each handle is right)
  socials: {
    instagram: "https://www.instagram.com/preski_fitness",
    tiktok: "https://www.tiktok.com/@preski_fitness",
    youtube: "https://www.youtube.com/@preski_fitness",
    snapchat: "https://www.snapchat.com/add/preski_fitness"
  },

  // Free guides. Keys must match netlify/lib/config.mjs on the server.
  guides: {
    blueprint: { title: "The Home Shred Blueprint", file: "guides/home-shred-blueprint.pdf" },
    abs:       { title: "28-Day Home Abs Challenge", file: "guides/28-day-home-abs.pdf" },
    shopping:  { title: "The UK Cutting Shopping List", file: "guides/cutting-shopping-list.pdf" },
    kickstart: { title: "3-Day Fat Loss Kickstart", file: "guides/3-day-fat-loss-kickstart.pdf" },
    calories:  { title: "How to Calculate Your Maintenance Calories", file: "guides/maintenance-calories-guide.pdf" }
  }
};
