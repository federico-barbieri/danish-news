(() => {
  const CACHE_PREFIX = "tr:";
  const MAX_CONCURRENCY = 4;
  const key = (body) => CACHE_PREFIX + (body.paragraph_id ?? `title:${body.article_id}`);

  const memory = new Map();
  function cached(body) {
    const k = key(body);
    if (memory.has(k)) return memory.get(k);
    try { const v = localStorage.getItem(k); if (v) { memory.set(k, v); return v; } } catch {}
    return null;
  }
  function store(body, text) {
    const k = key(body);
    memory.set(k, text);
    try { localStorage.setItem(k, text); } catch {}
  }

  async function fetchTranslation(body) {
    const hit = cached(body);
    if (hit) return hit;
    const r = await fetch("/api/translate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) {
      let msg = `Translation failed (${r.status})`;
      try { msg = (await r.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    const { text_en } = await r.json();
    store(body, text_en);
    document.dispatchEvent(new Event("usage:refresh"));
    return text_en;
  }

  function bodyFor(el) {
    return el.dataset.pid
      ? { paragraph_id: Number(el.dataset.pid) }
      : { article_id: Number(el.dataset.titleId), field: "title" };
  }
  const targetOf = (el) => el.nextElementSibling;

  async function show(el) {
    const out = targetOf(el);
    out.hidden = false;
    el.setAttribute("aria-expanded", "true");
    out.classList.remove("error");
    if (out.dataset.loaded) { out.textContent = out.dataset.loaded; out.classList.remove("loading"); return; }
    out.classList.add("loading");
    out.textContent = "Translating…";
    try {
      const text = await fetchTranslation(bodyFor(el));
      out.dataset.loaded = text;
      if (el.getAttribute("aria-expanded") === "true") out.textContent = text;
      out.classList.remove("loading");
    } catch (e) {
      out.classList.remove("loading");
      out.classList.add("error");
      out.textContent = e.message;
    }
  }
  function hide(el) {
    targetOf(el).hidden = true;
    el.setAttribute("aria-expanded", "false");
  }
  const isOpen = (el) => el.getAttribute("aria-expanded") === "true";
  const toggle = (el) => (isOpen(el) ? hide(el) : show(el));

  const items = [...document.querySelectorAll(".tr")];
  items.forEach((el) => {
    el.setAttribute("aria-expanded", "false");
    el.addEventListener("click", () => {
      if (getSelection().toString()) return; // don't toggle while selecting text
      toggle(el);
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(el); }
    });
  });

  const btn = document.getElementById("toggle-all");
  btn?.addEventListener("click", async () => {
    const on = btn.getAttribute("aria-pressed") !== "true";
    btn.setAttribute("aria-pressed", String(on));
    btn.textContent = on ? "Hide all translations" : "Show all translations";
    if (!on) { items.forEach(hide); return; }
    const queue = items.filter((el) => !isOpen(el));
    await Promise.all(Array.from({ length: MAX_CONCURRENCY }, async () => {
      while (queue.length) await show(queue.shift());
    }));
  });
})();
