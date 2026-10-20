// netbird-gitops portal.
// NetBird enforces access in the network: a policy that does not grant a tool drops the
// packets. So the page probes every tool from this device and only reveals the ones that
// answer. A tool that is not permitted is never displayed.
(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const text = document.body.dataset;
  const timeout = Number(text.timeout) || 4000;
  const list = $("#tools");
  const cards = Array.from(list.querySelectorAll(".card"));
  const summary = $("#summary");
  const announce = $("#announce");
  const input = $("#q");
  const recheck = $("#recheck");
  const noMatch = $("#no-match");
  const none = $("#none");
  // Re-checks when the tab is shown again are spaced by at least this much.
  const recheckAfter = 30000;
  let checking = false;
  let announceChecking = true;
  let lastCheck = 0;
  let run = 0;
  let summaryTimer;

  const fold = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const fill = (template, values) => template.replace(/\{(\w+)\}/g, (_, k) => values[k] ?? "");
  cards.forEach((card) => { card.dataset.search = fold(card.dataset.search); });

  // http: the request must get an HTTP answer. tcp: any answer before the timeout (even a
  // protocol error) proves the port is open; blocked packets only ever time out.
  const probe = async (card) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      // HEAD: no body is downloaded; any answer, even 405, still proves access.
      await fetch(card.dataset.probe, { method: "HEAD", mode: "no-cors", cache: "no-store", credentials: "omit", signal: controller.signal });
      return true;
    } catch {
      return card.dataset.mode === "tcp" && !controller.signal.aborted;
    } finally {
      clearTimeout(timer);
    }
  };

  const describe = (available, shown, query) => {
    if (checking && announceChecking) return text.textChecking;
    if (!available) return fill(text.textAvailable, { count: 0 });
    if (query) return fill(text.textMatching, { shown, count: available });
    return available === 1 ? text.textAvailableOne : fill(text.textAvailable, { count: available });
  };

  // Show the matching reachable cards and the right state; `quiet` delays the status
  // update so a screen reader is not interrupted at every keystroke.
  const render = (quiet = false) => {
    const query = fold(input.value);
    let available = 0;
    let shown = 0;
    for (const card of cards) {
      const ok = card.classList.contains("ok");
      const match = !query || card.dataset.search.includes(query);
      card.hidden = !match;
      if (ok) available += 1;
      if (ok && match) shown += 1;
    }
    $("#no-match-query").textContent = input.value.trim();
    noMatch.hidden = !(query && available && !shown);
    none.hidden = checking || available > 0;
    list.classList.toggle("has-results", available > 0);
    clearTimeout(summaryTimer);
    // Rewriting an unchanged message would make screen readers announce it again.
    const update = () => {
      const message = describe(available, shown, query);
      if (summary.textContent !== message) summary.textContent = message;
    };
    if (quiet) summaryTimer = setTimeout(update, 500);
    else update();
  };

  // Cards are updated in place as answers arrive: a re-check never blanks the list, a
  // tool that became reachable appears, one that no longer is disappears.
  // `manual`: the user asked, so "Checking…" is announced; automatic re-checks stay quiet.
  const check = async (manual = true) => {
    const current = ++run;
    checking = true;
    announceChecking = manual;
    recheck.disabled = true;
    list.setAttribute("aria-busy", "true");
    render();
    await Promise.all(cards.map(async (card) => {
      const ok = await probe(card);
      if (current === run) {
        card.classList.toggle("ok", ok);
        render(true);
      }
    }));
    if (current !== run) return;
    checking = false;
    lastCheck = Date.now();
    recheck.disabled = false;
    list.removeAttribute("aria-busy");
    render();
  };

  // Search: deep link with ?q=, "/" to focus, Escape to clear.
  const params = new URLSearchParams(location.search);
  input.value = params.get("q") || "";
  input.addEventListener("input", () => {
    const url = new URL(location.href);
    if (input.value) url.searchParams.set("q", input.value);
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    render(true);
  });
  input.form.addEventListener("submit", (event) => event.preventDefault());
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && input.value) {
      input.value = "";
      input.dispatchEvent(new Event("input"));
    }
  });
  document.addEventListener("keydown", (event) => {
    const typing = event.target.closest("input, textarea, select, [contenteditable]");
    if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      input.focus();
    }
  });
  $("#clear").addEventListener("click", () => {
    input.value = "";
    input.dispatchEvent(new Event("input"));
    input.focus();
  });

  // Copy the address of a non-web tool.
  const canCopy = Boolean(navigator.clipboard && window.isSecureContext);
  document.querySelectorAll(".copy").forEach((button) => {
    if (!canCopy) {
      button.hidden = true;
      return;
    }
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
      } catch {
        return;
      }
      button.classList.add("done");
      button.querySelector("use").setAttribute("href", "#i-check");
      announce.textContent = fill(text.textCopied, { address: button.dataset.copy });
      setTimeout(() => {
        button.classList.remove("done");
        button.querySelector("use").setAttribute("href", "#i-copy");
        announce.textContent = "";
      }, 2000);
    });
  });

  // No polling: re-check when what a user can reach may have changed, i.e. when they come
  // back to the tab (VPN reconnected, group added) or when the network comes back.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && !checking && Date.now() - lastCheck > recheckAfter) check(false);
  });
  window.addEventListener("online", () => { if (!checking) check(false); });

  recheck.hidden = false;
  recheck.addEventListener("click", () => check());
  $("#retry").addEventListener("click", () => check());
  check();
})();
