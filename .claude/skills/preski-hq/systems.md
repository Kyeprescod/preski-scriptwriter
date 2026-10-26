# Preski systems registry

Edit this file when a system is added, renamed or retired. Each entry: what it is, how HQ checks it, what GREEN/AMBER/RED looks like, which skill owns it.

## 1. Content engine (scripts and hooks)
- **What:** `preski-scriptwriter` skill and its bank.
- **Check:** read `.claude/skills/preski-scriptwriter/content-bank.md`. Count Inbox, ranked, scripted, posted. Note ideas with no hook, scripted-but-unposted, and the Results table (are real numbers being recorded?).
- **AMBER:** fewer than 3 ranked ideas ready to film, or scripted videos not posted for 7+ days, or Results empty after posting.
- **RED:** bank empty, nothing scripted.
- **Owner:** `preski-scriptwriter`; also user skills `preski-caption-and-hook-writer` for quick captions.

## 2. Footage library
- **What:** `content-library-intelligence`, indexing 13,000+ clips on the laptop.
- **Check:** run `python3 .claude/skills/content-library-intelligence/scripts/clil.py --lib <lib> status` if the library folder is reachable (default `~/preski-library`, `$CLIL_LIB`). Look at tagged vs pending, cloud-only clips, duplicates reported, showcase clips found.
- **If the library is on his laptop and not in this session:** NOT CHECKED. Ask Kye to run menu option for `status`/`report` and paste the output.
- **AMBER:** large pending/untagged backlog, nightly tagging not running, no showcase clips collected.
- **RED:** library DB missing or tagging failing.
- **Owner:** `content-library-intelligence`. Rule: originals are read-only, never delete duplicates without Kye's approval.

## 3. Daily post and approvals
- **What:** Daily Post pack (`daily-post-v2/`, `daily_pack.py`), phone approval inbox (`approvals.json`), user skills `preski-daily-production-pack` and `preski-motion-reel`.
- **Check:** `daily-post-v2/GO-LIVE.md` for whether v2 is switched on (it needs Kye's yes); the newest `example-post-*.json` or latest pack; `approvals.json` in the library folder if reachable: items pending approval, approved, rejected, scheduled.
- **AMBER:** posts waiting on approval, bank has too few real video clips (reel quality), v2 built but not switched on.
- **RED:** no post produced for the scheduled day, or routine failing.
- **Owner:** Kye approves; the daily routine produces.

## 4. Website and coaching funnel
- **What:** `site-v2/` (landing page, guides, application form, thanks), `site/` (Netlify functions: apply, subscribe, checkout, Stripe webhook, health, chat).
- **Check:** `site-v2/DESIGN-NOTES.md` "Not yet proven" list; `site/netlify/functions/health.mjs` lists the settings that must be true (email, owner email, checkout, Stripe webhook, plan delivery). If the live URL is known and reachable, request `/api/health` and report `missing`.
- **AMBER:** v2 not deployed, items in "Not yet proven" still unproven (Kit sign-up test, `coaching-application` form in Netlify, privacy page not checked), `planCheckoutUrl` or `bookingUrl` unset.
- **RED:** health shows missing checkout or webhook, forms not receiving applications.
- **Owner:** Kye deploys (Netlify drag and drop); Claude builds.

## 5. Leads, inbox and bookings
- **What:** coaching applications, DMs keyed HOME / SHRED / PROTEIN / ABS, email replies, calls booked.
- **Check:** Gmail (unanswered coaching/application emails, last 7 days) and Calendar (calls today and this week) if connected. DMs live in Instagram and can't be read: ask Kye for the count of open DMs.
- **AMBER:** applications or replies unanswered over 24h.
- **RED:** a paying or booked client waiting without a reply.
- **Owner:** Kye replies; Claude can draft.

## 6. Money
- **What:** coaching sales, guide sales, costs.
- **Check:** only if an accounting or payments connector is connected (for example QuickBooks or Stripe). Otherwise NOT CHECKED and ask for a weekly figure: revenue, new clients, cancellations.
- **Never** move money, send invoices or change prices.

## 7. Performance
- **What:** what's actually working on Instagram, TikTok and Shorts.
- **Check:** `content-bank.md` Results table, plus any exported numbers Kye gives. Compare against benchmarks: weighted crunches 68K, dumbbell-only 30K, under-25-minutes home workout 28K.
- **AMBER:** no numbers recorded in the last 7 days.
- **Owner:** Kye supplies numbers; `preski-scriptwriter` uses them to rescore.
