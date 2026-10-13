/* Preski Fitness: site behaviour (no libraries).
   Rules this file follows:
   - A form NEVER pretends it worked. If the server could not send the email, the visitor is told.
   - A missing answer is named, highlighted and scrolled to.
   - Works on phones: nothing relies on hover, and nothing is hidden behind a silent failure. */
(function () {
  "use strict";
  var C = window.PRESKI_CONFIG || {};

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function validEmail(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(v).trim()); }
  function go(url) { window.location.href = url; }
  function store(op, key, val) {
    try { return op === "get" ? window.sessionStorage.getItem(key) : op === "set" ? window.sessionStorage.setItem(key, val) : window.sessionStorage.removeItem(key); }
    catch (e) { return null; }
  }

  /* ---------- Fill prices, socials, links from config ---------- */
  function fill() {
    var p = C.prices || {};
    var map = { coachingMonthly: p.coachingMonthly, coachingNote: p.coachingNote, plan: p.plan, planNote: p.planNote };
    $$("[data-price]").forEach(function (el) { var v = map[el.getAttribute("data-price")]; if (v) el.textContent = v; });
    var s = C.socials || {};
    $$("[data-social]").forEach(function (el) { var v = s[el.getAttribute("data-social")]; if (v) el.href = v; else el.hidden = true; });
    $$("[data-booking]").forEach(function (el) { if (C.bookingUrl) el.href = C.bookingUrl; else el.hidden = true; });
    $$("[data-contact-email]").forEach(function (el) {
      if (!C.contactEmail) return;
      el.textContent = C.contactEmail;
      if (el.tagName === "A") el.href = "mailto:" + C.contactEmail;
    });
    var year = $("#year"); if (year) year.textContent = new Date().getFullYear();
  }

  /* ---------- Mobile menu ---------- */
  function setupMenu() {
    var toggle = $(".nav-toggle"), menu = $("#mobile-menu");
    if (!toggle || !menu) return;
    function setOpen(open) {
      menu.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      document.documentElement.classList.toggle("menu-open", open);
    }
    toggle.addEventListener("click", function () { setOpen(menu.hidden); });
    menu.addEventListener("click", function (e) { if (e.target.closest("a")) setOpen(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !menu.hidden) { setOpen(false); toggle.focus(); } });
    window.addEventListener("resize", function () { if (window.innerWidth > 820 && !menu.hidden) setOpen(false); });
  }

  /* ---------- Talking to the server ---------- */
  function postJSON(url, data) {
    var ctrl = "AbortController" in window ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 25000) : null;
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) { var e = new Error(body.error || "request_failed"); e.status = r.status; e.data = body; throw e; }
        return body;
      });
    }).then(function (v) { clearTimeout(timer); return v; }, function (e) {
      clearTimeout(timer);
      if (!e.status) e.network = true;
      throw e;
    });
  }

  /* ---------- Field-level errors ---------- */
  function containerOf(control) { return control.closest(".field") || control.closest(".consent") || control.parentNode; }
  function setError(container, message) {
    container.classList.add("has-error");
    var note = $(".field-err", container);
    if (!note) { note = document.createElement("p"); note.className = "field-err"; container.appendChild(note); }
    note.textContent = message;
    $$("input, textarea, select", container).forEach(function (c) { c.setAttribute("aria-invalid", "true"); });
  }
  function clearError(container) {
    container.classList.remove("has-error");
    var note = $(".field-err", container); if (note) note.remove();
    $$("[aria-invalid]", container).forEach(function (c) { c.removeAttribute("aria-invalid"); });
  }
  function clearOnEdit(form) {
    function handler(e) { var c = containerOf(e.target); if (c && c.classList.contains("has-error")) clearError(c); }
    form.addEventListener("input", handler);
    form.addEventListener("change", handler);
  }
  function showMsg(el, text, kind) {
    el.className = "form-msg" + (kind ? " " + kind : "");
    el.textContent = text;
  }
  function focusFirst(container) {
    if (!container) return;
    try { container.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) { container.scrollIntoView(); }
    var c = $("input:not([type=hidden]), textarea, select", container);
    if (c) { try { c.focus({ preventScroll: true }); } catch (e) { c.focus(); } }
  }

  /* ---------- Free guide form ---------- */
  var guideForm = $("#guide-form");
  if (guideForm) {
    var gmsg = $(".form-msg", guideForm);
    var guideRadios = $$("input[name=guide]", guideForm);
    function markGuide() { guideRadios.forEach(function (r) { r.parentNode.classList.toggle("is-checked", r.checked); }); }
    guideRadios.forEach(function (r) { r.addEventListener("change", markGuide); });
    markGuide();
    clearOnEdit(guideForm);

    guideForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var nameEl = $("#g-name"), emailEl = $("#g-email"), consentEl = $("#g-consent");
      var guide = ($("input[name=guide]:checked", guideForm) || {}).value || "blueprint";
      var problems = [];
      [nameEl, emailEl, consentEl].forEach(function (c) { clearError(containerOf(c)); });
      if (!nameEl.value.trim()) problems.push([nameEl, "Add your first name so I know who I'm talking to."]);
      if (!validEmail(emailEl.value)) problems.push([emailEl, "That email doesn't look right. Check it and try again."]);
      if (!consentEl.checked) problems.push([consentEl, "Tick the box so I can email you the guide."]);
      if (problems.length) {
        problems.forEach(function (p) { setError(containerOf(p[0]), p[1]); });
        showMsg(gmsg, "Please fix the highlighted " + (problems.length === 1 ? "question" : "questions") + ".", "err");
        focusFirst(containerOf(problems[0][0]));
        return;
      }
      var btn = $("button[type=submit]", guideForm);
      btn.disabled = true; btn.textContent = "Sending…"; showMsg(gmsg, "");
      postJSON("/api/subscribe", {
        email: emailEl.value.trim(), first_name: nameEl.value.trim(), guide: guide, consent: true,
        contact_me_by_fax_only: ($("[name=contact_me_by_fax_only]", guideForm) || {}).value || ""
      }).then(function () {
        go("thanks.html#" + guide);
      }).catch(function (err) {
        btn.disabled = false; btn.textContent = "Send me the guide";
        if (err.status === 422 && err.data && err.data.fields) {
          var map = { first_name: nameEl, email: emailEl, consent: consentEl };
          var first = null;
          Object.keys(err.data.fields).forEach(function (k) { if (map[k]) { setError(containerOf(map[k]), err.data.fields[k]); first = first || containerOf(map[k]); } });
          showMsg(gmsg, "Please fix the highlighted questions.", "err");
          focusFirst(first);
          return;
        }
        var g = (C.guides || {})[guide];
        gmsg.className = "form-msg err"; gmsg.textContent = "";
        var lead = err.status === 429 ? "Too many tries from this device. Wait a few minutes and try again. "
          : err.network ? "It looks like you're offline or the connection dropped. " : "I couldn't send the email just now. ";
        gmsg.appendChild(document.createTextNode(lead));
        if (g) {
          var a = document.createElement("a"); a.href = g.file; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Download the guide here instead";
          gmsg.appendChild(a); gmsg.appendChild(document.createTextNode(", then try the email again later."));
        }
      });
    });
  }

  /* ---------- Coaching application (3 steps) ---------- */
  var applyForm = $("#apply-form");
  if (applyForm) {
    var steps = $$(".fieldset", applyForm);
    var bars = $$(".progress span");
    var back = $("#apply-back"), next = $("#apply-next"), submit = $("#apply-submit");
    var amsg = $(".form-msg", applyForm);
    var cur = 0;
    var NAMES = {
      goal: "What you want most", why: "Why now", experience: "Training experience", equipment: "Equipment at home",
      days: "Days a week you can train", investment: "Ready to invest in coaching", name: "First name", email: "Email",
      consent: "Permission to contact you"
    };
    var DRAFT_KEY = "preski-apply-draft";

    function show(n) {
      cur = n;
      steps.forEach(function (s, k) { s.hidden = k !== n; });
      bars.forEach(function (b, k) { b.classList.toggle("on", k <= n); });
      back.hidden = n === 0;
      next.hidden = n === steps.length - 1;
      submit.hidden = n !== steps.length - 1;
    }
    function topOfForm() { try { applyForm.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) { applyForm.scrollIntoView(); } }

    // The unanswered questions in one step: [{container, name, message}]
    function problemsIn(n) {
      var out = [];
      $$(".field, .consent", steps[n]).forEach(function (box) {
        var req = $("[required]", box);
        if (!req) return;
        var name = req.name, ok = true, message = "Please answer this question.";
        if (req.type === "radio") ok = !!$("input[name='" + name + "']:checked", applyForm);
        else if (req.type === "checkbox") { ok = req.checked; message = "Tick the box so I can contact you."; }
        else if (!String(req.value).trim()) ok = false;
        else if (req.type === "email" && !validEmail(req.value)) { ok = false; message = "That email doesn't look right."; }
        if (!ok) out.push({ container: box, name: name, message: message });
      });
      return out;
    }
    function report(problems) {
      problems.forEach(function (p) { setError(p.container, p.message); });
      var names = problems.map(function (p) { return NAMES[p.name] || p.name; });
      showMsg(amsg, "You haven't answered: " + names.join(", ") + ".", "err");
      focusFirst(problems[0].container);
    }
    function validateStep(n) {
      $$(".has-error", steps[n]).forEach(clearError);
      var p = problemsIn(n);
      if (p.length) { report(p); return false; }
      showMsg(amsg, "");
      return true;
    }

    next.addEventListener("click", function () { if (validateStep(cur)) { show(cur + 1); topOfForm(); } });
    back.addEventListener("click", function () { showMsg(amsg, ""); show(cur - 1); topOfForm(); });
    clearOnEdit(applyForm);
    show(0);

    /* keep answers if the page reloads by accident */
    function saveDraft() {
      var d = {};
      $$("[name]", applyForm).forEach(function (c) {
        if (c.name === "contact_me_by_fax_only") return;
        if (c.type === "radio") { if (c.checked) d[c.name] = c.value; }
        else if (c.type === "checkbox") d[c.name] = c.checked;
        else d[c.name] = c.value;
      });
      store("set", DRAFT_KEY, JSON.stringify(d));
    }
    function restoreDraft() {
      var raw = store("get", DRAFT_KEY); if (!raw) return;
      var d; try { d = JSON.parse(raw); } catch (e) { return; }
      $$("[name]", applyForm).forEach(function (c) {
        if (!(c.name in d) || c.name === "contact_me_by_fax_only") return;
        if (c.type === "radio") c.checked = d[c.name] === c.value;
        else if (c.type === "checkbox") c.checked = !!d[c.name];
        else c.value = d[c.name];
      });
    }
    restoreDraft();
    applyForm.addEventListener("input", saveDraft);
    applyForm.addEventListener("change", saveDraft);

    applyForm.addEventListener("submit", function (e) {
      e.preventDefault();
      // Check EVERY step, not just the visible one
      for (var n = 0; n < steps.length; n++) {
        $$(".has-error", steps[n]).forEach(clearError);
        var p = problemsIn(n);
        if (p.length) { show(n); report(p); return; }
      }
      var v = function (name) { var c = $("[name='" + name + "']", applyForm); return c && c.type !== "radio" ? c.value : ""; };
      var chosen = function (name) { var c = $("input[name='" + name + "']:checked", applyForm); return c ? c.value : ""; };
      var payload = {
        goal: chosen("goal"), why: v("why"), experience: chosen("experience"), equipment: v("equipment"), days: chosen("days"),
        stats: v("stats"), blocker: v("blocker"), investment: chosen("investment"), name: v("name"), email: v("email"),
        instagram: v("instagram"), phone: v("phone"), consent: !!$("[name=consent]", applyForm).checked,
        contact_me_by_fax_only: v("contact_me_by_fax_only")
      };
      submit.disabled = true; submit.textContent = "Sending…"; showMsg(amsg, "");
      postJSON("/api/apply", payload).then(function () {
        store("remove", DRAFT_KEY);
        go("thanks.html#apply");
      }).catch(function (err) {
        submit.disabled = false; submit.textContent = "Send my application";
        if (err.status === 422 && err.data && err.data.fields) {
          var names = Object.keys(err.data.fields), firstStep = -1, found = [];
          names.forEach(function (k) {
            var c = $("[name='" + k + "']", applyForm); if (!c) return;
            var box = containerOf(c); setError(box, err.data.fields[k]);
            var s = steps.indexOf(c.closest(".fieldset")); if (firstStep < 0 || (s >= 0 && s < firstStep)) firstStep = s;
            found.push({ container: box, name: k, message: err.data.fields[k] });
          });
          if (found.length) { if (firstStep >= 0) show(firstStep); showMsg(amsg, "You haven't answered: " + found.map(function (f) { return NAMES[f.name] || f.name; }).join(", ") + ".", "err"); focusFirst(found[0].container); return; }
        }
        var why = err.status === 429 ? "Too many tries from this device. Wait a few minutes and try again."
          : err.network ? "It looks like you're offline or the connection dropped."
          : "Your application didn't send.";
        showMsg(amsg, why + " Your answers are saved, so try again in a moment, or DM me \"COACH\" on Instagram and I'll sort it.", "err");
      });
    });
  }

  /* ---------- Training plan checkout ---------- */
  $$("[data-checkout]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var note = $("#checkout-note");
      var label = btn.innerHTML;
      btn.setAttribute("aria-disabled", "true"); btn.textContent = "Opening checkout…";
      function restore() { btn.removeAttribute("aria-disabled"); btn.innerHTML = label; }
      postJSON("/api/checkout", {}).then(function (d) {
        if (!d || !d.url) throw new Error("no_url");
        go(d.url);
      }).catch(function (err) {
        restore();
        if (!note) return;
        note.hidden = false; note.className = "fine err-note";
        note.textContent = err.status === 503
          ? "Checkout isn't switched on yet. DM me \"PLAN\" on Instagram and I'll sort you out."
          : err.network ? "It looks like you're offline. Try again in a moment."
          : "Checkout couldn't open just now. Try again in a minute, or DM me \"PLAN\" on Instagram.";
      });
    });
  });

  /* ---------- Thank-you page ---------- */
  var thanks = $("#thanks");
  if (thanks) {
    var type = (location.hash || "").replace("#", "") || "blueprint";
    var g = (C.guides || {})[type];
    var panelType = g ? "guide" : type;
    var panels = $$("[data-type]", thanks), matched = false;
    panels.forEach(function (p) { var on = p.getAttribute("data-type") === panelType; p.hidden = !on; if (on) matched = true; });
    if (!matched && panels[0]) panels[0].hidden = false;
    $$("[data-guide-link]", thanks).forEach(function (a) { if (g) a.href = g.file; });
    $$("[data-guide-title]", thanks).forEach(function (el) { if (g) el.textContent = g.title; });
  }

  /* ---------- Before/after slider ---------- */
  var slider = $("#ba-slider");
  if (slider) {
    var range = $("#ba-range");
    var setPos = function (v) { slider.style.setProperty("--pos", v + "%"); };
    var touched = false;
    range.addEventListener("input", function () { touched = true; setPos(range.value); });
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        if (!entries[0].isIntersecting) return;
        io.disconnect();
        var keys = [50, 18, 82, 50], i = 0, start = null, dur = 700;
        function step(ts) {
          if (touched) return;
          if (!start) start = ts;
          var t = Math.min((ts - start) / dur, 1), e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
          var v = keys[i] + (keys[i + 1] - keys[i]) * e;
          setPos(v); range.value = v;
          if (t === 1) { i++; start = null; if (i >= keys.length - 1) return; }
          requestAnimationFrame(step);
        }
        setTimeout(function () { requestAnimationFrame(step); }, 400);
      }, { threshold: 0.5 });
      io.observe(slider);
    }
  }

  /* ---------- Transformation reel: clone the set for a seamless loop (CSS makes it swipeable on touch screens) ---------- */
  $$(".reel-track").forEach(function (track) {
    var set = $(".reel-set", track);
    if (!set) return;
    var copy = set.cloneNode(true);
    copy.setAttribute("aria-hidden", "true");
    $$("img", copy).forEach(function (img) { img.alt = ""; });
    track.appendChild(copy);
  });

  setupMenu();
  fill();
})();
