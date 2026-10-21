(function () {
  var C = window.PRESKI, $ = function (s) { return document.querySelector(s); };
  var chosen = Object.keys(C.guides)[0];

  // prices, links
  document.querySelectorAll("[data-price]").forEach(function (el) {
    var k = el.getAttribute("data-price");
    el.innerHTML = C.prices[k] + "<small>" + C.prices[k + "Note"] + "</small>";
  });
  $("#shredPrice").textContent = C.prices.shred;
  $("#shredOpen").textContent = C.shredDoorsOpen;
  if (C.planCheckoutUrl) { var b = $("#shredBtn"); b.href = C.planCheckoutUrl; b.textContent = "Join the 8-week shred"; b.removeAttribute("aria-disabled"); }
  if (C.bookingUrl) { var bk = $("#book"); bk.href = C.bookingUrl; bk.hidden = false; }
  $("#ig").href = C.socials.instagram; $("#tt").href = C.socials.tiktok; $("#yt").href = C.socials.youtube;

  // guide shelf
  var shelf = $("#shelf");
  Object.keys(C.guides).forEach(function (k) {
    var g = C.guides[k], li = document.createElement("li");
    li.innerHTML = '<button type="button" data-k="' + k + '" aria-pressed="false"><img src="' + g.cover + '" alt=""><span>' + g.title + "</span></button>";
    shelf.appendChild(li);
  });
  function pick(k, scroll) {
    if (!C.guides[k]) return;
    chosen = k;
    shelf.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.k === k)); });
    $("#got").className = "got"; $("#msg").textContent = ""; $("#msg").className = "msg";
    if (scroll) $("#guides").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth" });
  }
  shelf.addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) pick(b.dataset.k, false); });
  function fromHash() { var k = location.hash.replace("#", ""); if (C.guides[k]) pick(k, true); }
  addEventListener("hashchange", fromHash);
  pick(chosen, false); fromHash();

  // Kit sign-up (Kit's confirmation email is off, so the guide is shown straight away)
  $("#signup").addEventListener("submit", function (e) {
    e.preventDefault();
    var email = $("#email").value.trim(), msg = $("#msg"), got = $("#got"), btn = e.target.querySelector("button[type=submit]");
    msg.className = "msg"; got.className = "got";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { msg.textContent = "Enter a valid email address, like you@example.com."; msg.className = "msg err"; $("#email").focus(); return; }
    btn.disabled = true; msg.textContent = "Sending...";
    var fd = new FormData(); fd.append("email_address", email);
    fetch(C.kit.endpoint, { method: "POST", body: fd, mode: "no-cors" }).then(function () {
      var g = C.guides[chosen];
      msg.textContent = "";
      got.innerHTML = "You're in. <a href=\"" + g.file + "\" download>Download " + g.title + "</a>";
      got.className = "got on";
    }).catch(function () {
      msg.textContent = "That didn't go through. Check your connection and try again."; msg.className = "msg err";
    }).then(function () { btn.disabled = false; });
  });
})();
