# Preski Fitness site v2: design plan (frontend-design skill)

**Subject:** Kye, a UK home-training fitness coach. Audience: men who want to lose fat and build a visible physique without a gym. Job of the page: get an email (free guide) or a coaching application.

**Palette (taken from the eagle logo, not a template default):** Eagle navy `#052148`, Deep navy `#0A3170`, Signal red `#E1262D`, Fog `#EEF1F6`, Chalk `#FFFFFF`, Slate `#44526E`.

**Type:** Big Shoulders Display (condensed, athletic signage) for headlines, Figtree for reading text. Headlines in sentence case, one colour, no accent word. Self-hosted.

**Layout:** Hero = headline left on navy, tall real photo bleeding off the right edge. Directly under it a flush filmstrip of three real action photos (the gym is parks, gardens, back doors). Guides are shown as a row of real cover images, not identical cards. Coaching is a two-row price ledger on navy. No card grid, no gradient washes, no eyebrow labels, no scroll-reveal on every section.

**The one bold thing:** the headline type + the photo bleed. Everything else stays quiet.

**Review against the brief:** first draft would have been dark navy + big stat row + three rounded feature cards. Replaced the stat row (no verified numbers exist) with the filmstrip of real photos, and the cards with a ledger and a cover shelf.

**Functional rules kept from the live site:** guide sign-ups go to Kit form 10064261 (and the guide is shown to download straight away because Kit's confirmation email is off); coaching application is a Netlify Form named `coaching-application`; deep links `/#abs /#shopping /#blueprint /#kickstart /#calories`; prices from config.js; £29 shred link stays disabled until `planCheckoutUrl` is set; `bookingUrl` shows a button only when set.

## Deploying v2 (drag and drop, as you do now)
1. Download this branch as a zip from GitHub (or copy the `site-v2` folder to your laptop).
2. In Netlify: Deploys, then drag the **contents of `site-v2`** (the folder with `index.html` at the top) onto the deploy box.
3. Netlify Forms detection must stay ON: `apply.html` carries the `coaching-application` form.
4. Open `assets/js/config.js` to change prices, links, `planCheckoutUrl` and `bookingUrl`.

## Not yet proven
- Kit form 10064261 receiving the sign-up (it posts to `https://app.kit.com/forms/10064261/subscriptions` with `email_address`; test once and check Kit, then Subscribers).
- The `coaching-application` form appearing in Netlify, then Forms, after the first deploy.
- `privacy.html` is a plain-English draft: have it checked.
- Copy on the pages (captions, FAQ, "How it works") is written from your handover note, not from your live site: edit anything that isn't true.

Tests: `npm i playwright-core`, serve the folder on port 8811 (`python3 -m http.server 8811`), then `node e2e.mjs` (needs Chromium). 15 checks, all passing on the build.
