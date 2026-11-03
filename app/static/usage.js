(() => {
  const el = document.getElementById("usage");
  if (!el) return;
  async function refresh() {
    try {
      const { used, limit } = await (await fetch("/api/usage")).json();
      if (limit) el.textContent = `${Math.max(0, limit - used).toLocaleString("en")} chars left`;
    } catch {}
  }
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  document.addEventListener("usage:refresh", refresh); // fired by reader.js after a new translation
})();
