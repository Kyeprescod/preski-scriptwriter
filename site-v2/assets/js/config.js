/* PRESKI FITNESS: every number, price and link you may want to change lives here. */
window.PRESKI = {
  contactEmail: "hello@preskifitness.com",
  kit: { formId: "10064261", endpoint: "https://app.kit.com/forms/10064261/subscriptions" },
  prices: {
    monthly: "£250", monthlyNote: "per month",
    twelveWeek: "£675", twelveWeekNote: "for 12 weeks",
    founding: "£150", foundingNote: "per month, first 3 clients only",
    shred: "£29", shredNote: "Dumbbell Only 8-Week Shred"
  },
  shredDoorsOpen: "22 November",
  planCheckoutUrl: "",      // paste the Stripe payment link here when it exists; the button stays off until then
  bookingUrl: "",           // optional Calendly / Cal.com link; hidden when empty
  socials: {
    instagram: "https://www.instagram.com/preski_fitness",
    tiktok: "https://www.tiktok.com/@preski_fitness",
    youtube: "https://www.youtube.com/@preski_fitness"
  },
  guides: {
    blueprint: { title: "The Home Shred Blueprint", file: "guides/home-shred-blueprint.pdf", cover: "assets/img/guide-blueprint.jpg", line: "The full plan for losing fat at home." },
    abs:       { title: "28-Day Home Abs Challenge", file: "guides/28-day-home-abs.pdf", cover: "assets/img/guide-abs.jpg", line: "Four weeks of abs work you can do on a mat." },
    shopping:  { title: "The UK Cutting Shopping List", file: "guides/cutting-shopping-list.pdf", cover: "assets/img/guide-shopping.jpg", line: "What to buy in a UK supermarket to get lean." },
    kickstart: { title: "3-Day Fat Loss Kickstart", file: "guides/3-day-fat-loss-kickstart.pdf", cover: "assets/img/guide-kickstart.jpg", line: "Three days to get moving and eating right." },
    calories:  { title: "Maintenance Calories Guide", file: "guides/maintenance-calories-guide.pdf", cover: "assets/img/guide-calories.jpg", line: "Work out how much you eat to stay the same weight." }
  }
};
