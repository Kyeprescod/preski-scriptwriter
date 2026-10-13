/* "Ask Preski" chat widget.
   Talks to /api/chat (Claude, see netlify/functions/chat.mjs).
   If that isn't reachable it falls back to built-in answers so visitors are never left hanging. */
(function () {
  var C = window.PRESKI_CONFIG || {};
  var P = C.prices || {};
  var avatar = "assets/img/sofia.jpg";
  var history = [];
  var busy = false;

  var GREETING = "Alright, I'm the Preski assistant. Ask me anything about training at home, the free guides, coaching or the 8-week plan.";
  var QUICK = ["Get the free guide", "How much is coaching?", "I've got no equipment", "Coaching or the plan?"];

  var fab = document.createElement("button");
  fab.className = "chat-fab"; fab.type = "button"; fab.id = "chat-fab";
  fab.setAttribute("aria-expanded", "false"); fab.setAttribute("aria-controls", "chat-panel");
  fab.innerHTML = '<img src="' + avatar + '" alt=""><span>Ask Preski</span>';

  var panel = document.createElement("section");
  panel.className = "chat-panel"; panel.id = "chat-panel"; panel.hidden = true;
  panel.setAttribute("aria-label", "Chat with the Preski assistant");
  panel.innerHTML =
    '<div class="chat-head"><img src="' + avatar + '" alt=""><div><div class="n">Preski assistant</div><div class="s">Usually replies instantly</div></div>' +
    '<button type="button" aria-label="Close chat" id="chat-close">×</button></div>' +
    '<div class="chat-log" id="chat-log" aria-live="polite"></div>' +
    '<div class="chat-quick" id="chat-quick"></div>' +
    '<form class="chat-form" id="chat-form"><label class="hp" for="chat-input">Message</label>' +
    '<input id="chat-input" autocomplete="off" placeholder="Type your question…" maxlength="600">' +
    '<button type="submit">Send</button></form>';

  // On the application page the floating button would sit on top of the form buttons on a phone.
  if (/apply(\.html)?\/?$/.test(location.pathname)) fab.classList.add("chat-fab--apply");
  document.body.appendChild(panel);
  document.body.appendChild(fab);

  var log = panel.querySelector("#chat-log");
  var quick = panel.querySelector("#chat-quick");
  var input = panel.querySelector("#chat-input");

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]; }); }
  // Allow simple [text](url) links in bot replies; everything else is escaped.
  function render(text) {
    return esc(text).replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/|[a-z0-9-]+\.html|#)[^)\s]*)\)/gi, '<a href="$2">$1</a>');
  }
  function add(role, text) {
    var d = document.createElement("div");
    d.className = "msg " + (role === "user" ? "me" : "bot");
    d.innerHTML = role === "user" ? esc(text) : render(text);
    log.appendChild(d); log.scrollTop = log.scrollHeight;
    return d;
  }
  function setQuick(list) {
    quick.innerHTML = "";
    list.forEach(function (q) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = q;
      b.addEventListener("click", function () { send(q); });
      quick.appendChild(b);
    });
  }

  function open() {
    panel.hidden = false; fab.setAttribute("aria-expanded", "true");
    if (!log.children.length) { add("assistant", GREETING); history.push({ role: "assistant", content: GREETING }); setQuick(QUICK); }
    setTimeout(function () { input.focus(); }, 50);
  }
  function close() { panel.hidden = true; fab.setAttribute("aria-expanded", "false"); fab.focus(); }
  fab.addEventListener("click", function () { panel.hidden ? open() : close(); });
  panel.querySelector("#chat-close").addEventListener("click", close);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(); });

  /* ---- Offline answers (used when the AI backend isn't connected) ---- */
  function fallback(q) {
    var t = q.toLowerCase();
    if (/abs|core|six.?pack|crunch/.test(t))
      return "Grab the free 28-Day Home Abs Challenge: 12 minutes, 3 times a week, built on the routine from my most-viewed video. Remember abs are shown by low body fat, so pair it with a small calorie deficit. [Get it here](#guide)";
    if (/shop|grocer|snack|takeaway|nando|supermarket/.test(t))
      return "The free UK Cutting Shopping List has what to buy at Tesco, Aldi or Lidl, 15 high-protein snacks, 5 quick meals and what to order at a takeaway. [Get it here](#guide)";
    if (/guide|free|pdf|kickstart|download|calorie|blueprint/.test(t))
      return "Start with the free Home Shred Blueprint: your calories, protein, a 4-day home training plan and how to progress it. There's also a 28-day abs challenge, a cutting shopping list and a 3-day kickstart. [Pick one here](#guide)";
    if (/price|cost|how much|£|afford|expensive|cheap/.test(t))
      return "1:1 coaching is " + (P.coachingMonthly || "£149") + " " + (P.coachingNote || "per month") + ". If that's too much right now, the 8-Week Home Shred Programme is " + (P.plan || "£39") + " one-off: same training style, you just run it yourself. [See the plan](plan.html)";
    if (/equipment|no gym|home|dumbbell|kit|space/.test(t))
      return "You don't need a gym. My own setup is two 12.5 kg dumbbells, a captain's chair, the floor and a wall. If you've got nothing at all, we start with bodyweight and a backpack and build from there.";
    if (/coach|plan|differ|which|vs|or the/.test(t))
      return "Coaching = I build everything around you, check in every week and adjust your food and training. The plan = a proven 8-week programme you follow on your own. If you want accountability and faster results, coaching. If budget's tight, the plan. [Apply for coaching](apply.html)";
    if (/beginner|start|never|unfit|overweight|old/.test(t))
      return "Beginners are welcome. Everything has an easier version and we build up week by week. Best first step: grab the free 3-Day Kickstart [here](#guide).";
    if (/diet|eat|food|protein|meal/.test(t))
      return "Simple version: eat enough protein (roughly 1.6–2.2 g per kg of bodyweight), keep a small calorie deficit, and don't ban foods you love. The free maintenance-calories guide shows you how to find your numbers. [Get it here](#guide)";
    if (/apply|sign up|join|start coaching|spots/.test(t))
      return "Love that. The application takes about 3 minutes and I read every one personally. [Start your application](apply.html)";
    if (/refund|cancel|guarantee/.test(t))
      return "Good question. Kye will confirm the exact terms on your call before you pay anything, so you're never locked into something you're unsure about.";
    if (/hello|hi|hey|yo|alright/.test(t))
      return "Alright! What are you working towards: losing fat, building muscle, or both?";
    return "Good question. I'll make sure Kye sees that. In the meantime, the quickest way to get a proper answer is to [apply for coaching](apply.html) or DM \"COACH\" on Instagram.";
  }

  function send(text) {
    text = String(text || "").trim();
    if (!text || busy) return;
    busy = true; setQuick([]);
    add("user", text); history.push({ role: "user", content: text });
    var typing = add("assistant", "Typing…"); typing.classList.add("typing");

    fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history.slice(-12), page: location.pathname })
    })
      .then(function (r) { if (!r.ok) throw new Error("chat"); return r.json(); })
      .then(function (d) { if (!d || !d.reply) throw new Error("empty"); return d.reply; })
      .catch(function () { return fallback(text); })
      .then(function (reply) {
        typing.remove();
        add("assistant", reply); history.push({ role: "assistant", content: reply });
        busy = false;
        setQuick(["Get the free guide", "Apply for coaching", "See the 8-week plan"]);
      });
  }

  panel.querySelector("#chat-form").addEventListener("submit", function (e) {
    e.preventDefault(); var v = input.value; input.value = ""; send(v);
  });

  // Quick-reply shortcuts that should navigate rather than chat
  quick.addEventListener("click", function (e) {
    var t = e.target.textContent;
    if (t === "Apply for coaching") { e.stopImmediatePropagation(); location.href = "apply.html"; }
    if (t === "See the 8-week plan") { e.stopImmediatePropagation(); location.href = "plan.html"; }
  }, true);

  // Links inside answers that point to #guide: close the chat so the form is visible
  log.addEventListener("click", function (e) {
    var a = e.target.closest("a"); if (!a) return;
    var h = a.getAttribute("href") || "";
    if (h === "#guide" && !document.getElementById("guide")) { e.preventDefault(); location.href = "./#guide"; }
    else if (h.charAt(0) === "#") close();
  });
})();
