# Preski Fitness website: going live (about 30 minutes)

The website is plain pages plus six small server programmes (in `netlify/functions`) that run on Netlify:

| What a visitor does | What happens automatically |
|---|---|
| Asks for a free guide | `/api/subscribe` emails them the guide link (and adds them to your subscriber list) |
| Submits the coaching application | `/api/apply` emails you every answer (your reply goes straight to them) and sends them a receipt |
| Taps "Get the programme" | `/api/checkout` opens Stripe, then `/api/stripe-webhook` emails them the programme the moment they've paid, and tells you |
| Uses the chat | `/api/chat` answers with Claude (or built-in answers if no key is set) |
| You open `/api/health` | Shows which of the above is connected (yes/no only, never your keys) |

If email can't be sent, the visitor is **told** (and given a direct download link for guides). Nothing pretends to work.

## Step 1: Put the site on Netlify
1. Make a free account at **netlify.com** (sign in with GitHub).
2. **Add new site, Import an existing project, GitHub**, then choose the `preski-scriptwriter` repository.
3. Branch to deploy: the branch these files are on (or merge them to `main` first).
4. **Base directory: `site`**. Build command: leave empty. Publish directory: `.`
5. Click **Deploy**. When it finishes you get an address like `something.netlify.app`.

## Step 2: Email (Resend), so guides, applications and plans can be sent
1. Make a free account at **resend.com**.
2. **Domains, Add domain**, then `preskifitness.com`. Resend shows a few DNS records: add them where you bought the domain, then click Verify. (Until you do this, Resend only lets you email yourself.)
3. **API Keys, Create** a key. Copy it.
4. In Netlify: **Site configuration, Environment variables**, add:
   - `RESEND_API_KEY` = the key
   - `MAIL_FROM` = `Kye at Preski Fitness <kye@preskifitness.com>`
   - `OWNER_EMAIL` = the address you want applications sent to
5. Optional: Resend **Audiences, Create**, copy its ID into `RESEND_AUDIENCE_ID` to keep a subscriber list.

## Step 3: Payments (Stripe)
1. At **stripe.com** (finish account activation), open **Developers, API keys** and copy the **Secret key**. Add it in Netlify as `STRIPE_SECRET_KEY`. (Start with the `sk_test_` key while testing.)
2. **Developers, Webhooks, Add endpoint.** Endpoint URL: `https://YOUR-SITE-ADDRESS/api/stripe-webhook`. Event to send: `checkout.session.completed`. Save, then copy its **Signing secret** (`whsec_...`) into Netlify as `STRIPE_WEBHOOK_SECRET`.
3. **The programme file.** Upload your finished 8-week programme PDF somewhere with a private share link (Google Drive "anyone with the link", Dropbox, etc.) and put that link in Netlify as `PLAN_DOWNLOAD_URL`.
   *The programme itself is not in this project, so this step is yours. If it is missing when someone pays, they get a "payment received, programme within 24 hours" email and **you** get an "ACTION NEEDED" email.*
4. Price: `PLAN_PRICE_PENCE` is what Stripe charges (3900 = £39). Keep it matching the price shown in `assets/js/config.js`.

## Step 4 (optional): Chat assistant
Make a key at **console.anthropic.com**, set a monthly spend limit there, and add it as `ANTHROPIC_API_KEY`. Without it the chat still works using built-in answers.

## Step 5: Your own address
Netlify **Domain management, Add a domain**, then `preskifitness.com`, and follow its DNS instructions. After changing any setting in Netlify, go to **Deploys, Trigger deploy** so it takes effect.

## Step 6: Test it (do all of these before announcing)
1. Open `https://YOUR-SITE/api/health`. Every item under `missing` must be gone. If something is listed, that step isn't finished.
2. On your phone: request a free guide with **your own email**. The email should arrive within a minute.
3. Fill in the coaching application: you should get the application and the applicant should get a receipt.
4. Test payment with Stripe **test mode** (`sk_test_` key): use card `4242 4242 4242 4242`, any future date, any CVC. The programme email should arrive.
5. Switch to your `sk_live_` key and the live webhook secret, redeploy, and do one real £39 purchase with your own card, then refund it in Stripe.

## Things to know
- **Costs:** Netlify, Resend (3,000 emails/month) and the chat are free or cheap at small scale; Stripe takes its normal fee per sale; Anthropic charges per chat message (set a spend limit).
- **Not built yet:** a "tips over the next week" email sequence. The site no longer promises one. It needs a subscriber database and a scheduler, and can be added.
- **Legal:** `privacy.html` is a plain-English template. Have it checked before launch, and set `contactEmail` in `assets/js/config.js` to an address you really read.
- **Social handles** in `config.js` are marked "check each handle is right".

## For developers
- `npm test` runs the 25 server tests (no network needed).
- `npm run dev:mock` starts the site with fake email/Stripe/Claude; `npm i -D playwright-core` then `npm run test:e2e` drives it in a phone-sized browser (74 checks).
- `npm run dev` runs the site locally against real services using a `.env` file (see `.env.example`).
