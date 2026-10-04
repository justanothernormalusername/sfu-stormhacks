// Shared helpers for every page (and the Phaser game).

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("Not logged in");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// Build an element with textContent (never innerHTML) so user text can't inject markup.
function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.message && e.reason.message !== "Not logged in") alert(e.reason.message);
});
