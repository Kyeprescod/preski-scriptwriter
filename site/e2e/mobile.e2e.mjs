// End-to-end checks in a real (Chromium) browser at phone size. Needs:  npm i playwright-core   and the dev server in mock mode:
//   DEV_MOCK=1 node scripts/dev-server.mjs   then   node e2e/mobile.e2e.mjs
import { chromium, devices } from "playwright-core";
import fs from "node:fs";

const BASE = process.env.BASE || "http://localhost:8890";
const CHROME = process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const SHOTS = process.env.SHOTS || "";
let pass = 0, fail = 0;
const ok = (cond, name, extra = "") => { if (cond) { pass++; console.log("  PASS", name); } else { fail++; console.log("  FAIL", name, extra); } };
const mode = (m) => fetch(`${BASE}/__mode?m=${m}`).then((r) => r.text());
const outbox = () => fetch(`${BASE}/__outbox`).then((r) => r.json());
const clear = () => fetch(`${BASE}/__outbox`, { method: "DELETE" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
const phone = { ...devices["iPhone 13"], viewport: { width: 390, height: 844 } };
const small = { ...devices["iPhone 13"], viewport: { width: 360, height: 740 } };

async function open(ctxOpts, path) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  await page.goto(BASE + path, { waitUntil: "load" });
  return { ctx, page, errors };
}
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false }); };

/* ---------- 1. every page: no sideways scroll, no JS errors, images load, menu works ---------- */
console.log("\n[1] Pages on phones");
for (const [label, vp] of [["390px", phone], ["360px", small]]) {
  for (const pg of ["/", "/apply.html", "/plan.html", "/thanks.html#plan", "/privacy.html"]) {
    const { ctx, page, errors } = await open(vp, pg);
    await sleep(300);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth,
      broken: [...document.images].filter((i) => i.complete && i.naturalWidth === 0 && i.currentSrc).map((i) => i.currentSrc.split("/").pop()),
      wide: [...document.querySelectorAll("body *")].filter((e) => { const r = e.getBoundingClientRect(); return r.right > window.innerWidth + 1 && r.width > 0 && getComputedStyle(e).position !== "fixed" && !e.closest(".reel,.strip,.hp,.mobile-menu"); }).slice(0, 3).map((e) => e.tagName + "." + e.className) }));
    ok(m.sw <= m.iw, `${label} ${pg}: no sideways scrolling`, `scrollWidth ${m.sw} > ${m.iw}; wide: ${m.wide.join(", ")}`);
    ok(m.broken.length === 0, `${label} ${pg}: images load`, m.broken.join(","));
    ok(errors.length === 0, `${label} ${pg}: no JavaScript errors`, errors.join(" | "));
    await ctx.close();
  }
}
{
  const { ctx, page } = await open(phone, "/");
  ok(await page.isVisible(".nav-toggle"), "menu button is visible on a phone");
  ok(!(await page.isVisible("#mobile-menu")), "menu starts closed");
  await page.tap(".nav-toggle");
  ok(await page.isVisible("#mobile-menu"), "tapping the button opens the menu");
  ok((await page.locator("#mobile-menu a:not(.btn)").count()) === 4, "menu lists the 4 sections");
  await page.tap("#mobile-menu a[href='#options']");
  await sleep(500);
  ok(!(await page.isVisible("#mobile-menu")), "choosing a link closes the menu");
  await shot(page, "01-home-menu-closed");
  await ctx.close();
}

/* ---------- 2. free guide form ---------- */
console.log("\n[2] Free guide form");
await mode("ok"); await clear();
{
  const { ctx, page } = await open(phone, "/");
  await page.locator("#guide").scrollIntoViewIfNeeded();
  await page.tap("#guide-form button[type=submit]");
  const err = await page.locator("#guide-form .form-msg").innerText();
  ok(/fix the highlighted questions/i.test(err), "empty form: says what to do", err);
  ok((await page.locator("#guide-form .has-error").count()) === 3, "empty form: highlights all 3 problems");
  ok(/first name/i.test(await page.locator("#guide-form .field-err").first().innerText()), "empty form: names the missing question");
  await shot(page, "02-guide-errors");
  await page.fill("#g-name", "Jo"); await page.fill("#g-email", "jo@example.com");
  ok((await page.locator("#guide-form .has-error").count()) === 1, "errors clear as you fix them");
  await page.tap("#g-abs", { force: true });
  await page.tap("#g-consent");
  await Promise.all([page.waitForURL(/thanks\.html#abs/), page.tap("#guide-form button[type=submit]")]);
  const mails = (await outbox()).filter((o) => o.url.includes("resend.com/emails"));
  ok(mails.length === 1 && mails[0].body.to[0] === "jo@example.com", "email really sent to the visitor");
  ok(/28-day-home-abs\.pdf/.test(mails[0].body.html), "email contains the chosen guide's link");
  ok(await page.isVisible("[data-type=guide]"), "thank-you page shows the guide panel");
  ok(/28-Day Home Abs/.test(await page.locator("[data-guide-title]").innerText()), "thank-you page names the right guide");
  await ctx.close();
}
await mode("email_down"); await clear();
{
  const { ctx, page } = await open(phone, "/");
  await page.fill("#g-name", "Jo"); await page.fill("#g-email", "jo@example.com"); await page.tap("#g-consent");
  await page.tap("#guide-form button[type=submit]");
  await page.waitForSelector("#guide-form .form-msg a");
  const msg = await page.locator("#guide-form .form-msg").innerText();
  ok(page.url().endsWith("/") || page.url().includes("#"), "email down: stays on the page (no fake success)", page.url());
  ok(/couldn't send/i.test(msg) && /download the guide here/i.test(msg), "email down: honest message with a direct download link", msg);
  ok(await page.isEnabled("#guide-form button[type=submit]"), "email down: button works again");
  await shot(page, "03-guide-email-down");
  await ctx.close();
}

/* ---------- 3. coaching application ---------- */
console.log("\n[3] Coaching application");
await mode("ok"); await clear();
{
  const { ctx, page } = await open(phone, "/apply.html");
  await page.tap("#apply-next");
  const m1 = await page.locator("#apply-form .form-msg").innerText();
  ok(/haven't answered/i.test(m1) && /What you want most/.test(m1) && /Why now/.test(m1) && /Training experience/.test(m1), "step 1: names every unanswered question", m1);
  ok((await page.locator("#apply-form .has-error").count()) === 3, "step 1: highlights all three");
  ok(!(await page.locator("#apply-form .fieldset").nth(1).isVisible()), "step 1: does not move on");
  await shot(page, "04-apply-errors");
  await page.tap("label.choice:has(#goal-1)");
  ok((await page.locator("#apply-form .has-error").count()) === 2, "step 1: error clears when a question is answered");
  await page.fill("#why", "Holiday in June");
  await page.tap("label.choice:has(#exp-1)");
  await page.tap("#apply-next");
  ok(await page.locator("#apply-form .fieldset").nth(1).isVisible(), "step 2 appears once step 1 is complete");
  await page.reload();
  ok((await page.inputValue("#why")) === "Holiday in June", "answers survive an accidental reload");
  await page.tap("#apply-next");
  await page.fill("#kit", "Dumbbells");
  await page.tap("label.choice:has(#days-2)");
  await page.tap("#apply-next");
  ok(await page.locator("#apply-form .fieldset").nth(2).isVisible(), "step 3 reached");
  await page.tap("#apply-submit");
  const m3 = await page.locator("#apply-form .form-msg").innerText();
  ok(/Ready to invest/.test(m3) && /First name/.test(m3) && /Email/.test(m3) && /Permission/.test(m3), "step 3: names what is missing", m3);
  await page.tap("label.choice:has(#inv-1)");
  await page.fill("#a-name", "Sam"); await page.fill("#a-email", "sam@example.com"); await page.fill("#a-ig", "@sam");
  await page.tap("#a-consent");
  await Promise.all([page.waitForURL(/thanks\.html#apply/), page.tap("#apply-submit")]);
  const mails = (await outbox()).filter((o) => o.url.includes("resend.com/emails"));
  ok(mails.length === 2, "Kye gets the application and Sam gets a receipt", String(mails.length));
  ok(mails[0].body.to[0] === "kye@example.com" && /Holiday in June/.test(mails[0].body.html) && /Dumbbells/.test(mails[0].body.html), "Kye's email contains the answers");
  ok(await page.isVisible("[data-type=apply]"), "thank-you page confirms the application");
  await ctx.close();
}
await mode("email_down"); await clear();
{
  const { ctx, page } = await open(phone, "/apply.html");
  await page.evaluate(() => sessionStorage.removeItem("preski-apply-draft"));
  await page.tap("label.choice:has(#goal-2)"); await page.fill("#why", "Wedding");
  await page.tap("label.choice:has(#exp-2)"); await page.tap("#apply-next");
  await page.fill("#kit", "Nothing"); await page.tap("label.choice:has(#days-1)"); await page.tap("#apply-next");
  await page.tap("label.choice:has(#inv-2)"); await page.fill("#a-name", "Sam"); await page.fill("#a-email", "sam@example.com"); await page.tap("#a-consent");
  await page.tap("#apply-submit");
  await page.waitForFunction(() => /didn't send/.test(document.querySelector("#apply-form .form-msg").textContent));
  const msg = await page.locator("#apply-form .form-msg").innerText();
  ok(/COACH/.test(msg) && /saved/.test(msg), "email down: honest message, answers kept", msg);
  ok(page.url().includes("apply.html"), "email down: no fake success page");
  ok((await page.inputValue("#a-name")) === "Sam" && await page.isEnabled("#apply-submit"), "email down: form still filled and button works again");
  await ctx.close();
}

/* ---------- 4. checkout ---------- */
console.log("\n[4] 8-week plan checkout");
await mode("unconfigured");
{
  const { ctx, page } = await open(phone, "/plan.html");
  await page.tap("header [data-checkout]");
  await page.waitForSelector("#checkout-note:not([hidden])");
  ok(/isn't switched on yet/.test(await page.locator("#checkout-note").innerText()), "not set up: friendly message, not a dead button");
  await ctx.close();
}
await mode("ok"); await clear();
{
  const { ctx, page } = await open(phone, "/plan.html");
  let went = "";
  await page.route("https://checkout.stripe.com/**", (r) => { went = r.request().url(); r.fulfill({ status: 200, contentType: "text/html", body: "stripe" }); });
  await page.tap("header [data-checkout]");
  await page.waitForURL(/checkout\.stripe\.com/);
  ok(went.includes("cs_mock"), "set up: goes to Stripe checkout");
  const stripe = (await outbox()).find((o) => o.url.includes("stripe.com"));
  ok(new URLSearchParams(String(stripe.body)).get("line_items[0][price_data][unit_amount]") === "3900", "charges £39 in GBP");
  await ctx.close();
}

/* ---------- 5. chat on a phone ---------- */
console.log("\n[5] Chat assistant on a phone");
await mode("chat");
{
  const { ctx, page } = await open(phone, "/");
  const fab = await page.locator("#chat-fab").boundingBox();
  ok(fab.width <= 64 && fab.height <= 64, "chat button is a small round icon on phones", JSON.stringify(fab));
  await page.tap("#chat-fab");
  const panel = await page.locator("#chat-panel").boundingBox();
  ok(panel.x >= 0 && panel.x + panel.width <= 390 && panel.y >= 0, "chat panel fits on screen", JSON.stringify(panel));
  const fs = await page.$eval("#chat-input", (e) => parseFloat(getComputedStyle(e).fontSize));
  ok(fs >= 16, "chat box text is 16px+ (iPhone will not zoom in)", String(fs));
  await page.fill("#chat-input", "How much is coaching?");
  await page.tap("#chat-form button");
  await page.waitForFunction(() => /Mock assistant reply/.test(document.querySelector("#chat-log").textContent), null, { timeout: 8000 });
  ok(true, "AI reply shows");
  await shot(page, "05-chat-open");
  await ctx.close();
}
await mode("unconfigured");
{
  const { ctx, page } = await open(phone, "/");
  await page.tap("#chat-fab"); await page.fill("#chat-input", "how much is coaching"); await page.tap("#chat-form button");
  await page.waitForFunction(() => /£149/.test(document.querySelector("#chat-log").textContent), null, { timeout: 8000 });
  ok(true, "no AI key: built-in answer still helps");
  await ctx.close();
}
{
  const { ctx, page } = await open(phone, "/apply.html");
  ok(!(await page.isVisible("#chat-fab")), "chat button hidden on the application page (cannot cover the form buttons)");
  await ctx.close();
}

/* ---------- 6. touch things ---------- */
console.log("\n[6] Touch behaviour");
{
  const { ctx, page } = await open(phone, "/");
  const reel = await page.$eval(".reel", (e) => ({ ox: getComputedStyle(e).overflowX, copyHidden: getComputedStyle(e.querySelector('.reel-set[aria-hidden="true"]')).display }));
  ok(reel.ox === "auto" && reel.copyHidden === "none", "photo reel is a normal swipeable strip on touch screens", JSON.stringify(reel));
  await page.locator("#ba-slider").scrollIntoViewIfNeeded(); await sleep(2200);
  const box = await page.locator("#ba-slider").boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.85, box.y + box.height * 0.5, { steps: 6 }); await page.mouse.up();
  const pos = parseFloat(await page.$eval("#ba-slider", (e) => e.style.getPropertyValue("--pos")));
  ok(pos > 70, "before/after slider can be dragged", String(pos));
  await shot(page, "06-slider");
  await ctx.close();
}

/* ---------- 7. desktop still fine ---------- */
console.log("\n[7] Desktop");
{
  const { ctx, page, errors } = await open({ viewport: { width: 1280, height: 800 } }, "/");
  ok(!(await page.isVisible(".nav-toggle")) && (await page.isVisible(".nav-links")), "desktop shows the normal menu, not the phone button");
  ok(await page.$eval("html", (e) => e.scrollWidth <= window.innerWidth), "desktop: no sideways scrolling");
  ok(errors.length === 0, "desktop: no JavaScript errors", errors.join("|"));
  await shot(page, "07-desktop");
  await ctx.close();
}

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
