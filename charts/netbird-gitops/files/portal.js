// netbird-gitops portal: probes each tool from the browser. A request that gets ANY answer
// (even an error page) means the network path is open; a timeout or a network error means
// the VPN policy blocks it, the name does not resolve, or the device is off the VPN.
(() => {
  "use strict";
  const data = document.body.dataset;
  const timeout = Number(data.timeout) || 4000;
  const cards = Array.from(document.querySelectorAll("[data-check]"));
  const summary = document.getElementById("summary");
  const button = document.getElementById("recheck");

  const fill = (template, values) => template.replace(/\{(\w+)\}/g, (_, k) => values[k] ?? "");

  const show = (card, state) => {
    const status = card.querySelector(".status");
    status.dataset.state = state;
    status.querySelector("use").setAttribute("href", `#i-${state}`);
    status.querySelector("span").textContent = data[`text${state[0].toUpperCase()}${state.slice(1)}`];
  };

  const probe = async (url) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      // no-cors: the answer is opaque, only its arrival matters (and it requires redirect: follow).
      await fetch(url, { mode: "no-cors", cache: "no-store", credentials: "omit", signal: controller.signal });
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  };

  const check = async () => {
    if (!cards.length) {
      summary.textContent = "";
      return;
    }
    button.disabled = true;
    summary.textContent = fill(data.textSummaryChecking, { total: cards.length });
    cards.forEach((card) => show(card, "checking"));
    const results = await Promise.all(cards.map(async (card) => {
      const ok = await probe(card.dataset.check);
      show(card, ok ? "reachable" : "blocked");
      return ok;
    }));
    summary.textContent = fill(data.textSummary, {
      reachable: results.filter(Boolean).length,
      total: results.length,
    });
    button.disabled = false;
  };

  button.hidden = cards.length === 0;
  button.addEventListener("click", check);
  check();
})();
