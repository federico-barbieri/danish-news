(async () => {
  const el = document.getElementById("usage");
  if (!el) return;
  try {
    const r = await fetch("/api/usage");
    const { used, limit } = await r.json();
    if (limit) el.textContent = `${Math.max(0, limit - used).toLocaleString("en")} chars left`;
  } catch {}
})();
