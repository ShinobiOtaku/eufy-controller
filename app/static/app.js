(() => {
  "use strict";

  const labels = {
    away: { title: "Away", description: "Full monitoring is active", glyph: "M22 36.5 29 43l14-16" },
    schedule: { title: "Schedule", description: "Following your Eufy timetable", glyph: "M20 27h24v23H20V27Zm0 8h24M26 22v9m12-9v9m-6 8v6l4 2" },
    unknown: { title: "Unknown", description: "The security mode could not be confirmed", glyph: "M32 24v13m0 9v1" },
  };

  const elements = {
    connection: document.querySelector("#connection"),
    connectionLabel: document.querySelector("#connection-label"),
    demoBanner: document.querySelector("#demo-banner"),
    modeLabel: document.querySelector("#mode-label"),
    modeDescription: document.querySelector("#mode-description"),
    confirmed: document.querySelector("#confirmed"),
    shield: document.querySelector("#shield"),
    shieldGlyph: document.querySelector("#shield-glyph"),
    provider: document.querySelector("#provider"),
    message: document.querySelector("#message"),
    buttons: [...document.querySelectorAll(".mode-button")],
    refresh: document.querySelector("#refresh"),
  };

  let csrf = "";
  let currentMode = "unknown";
  let busy = false;

  const apiUrl = (path) => new URL(path, window.location.href).toString();

  function relativeTime(epochSeconds) {
    if (!epochSeconds) return "Confirmation time unavailable";
    const seconds = Math.max(0, Math.round(Date.now() / 1000 - epochSeconds));
    if (seconds < 5) return "Confirmed just now";
    if (seconds < 60) return `Confirmed ${seconds} seconds ago`;
    const minutes = Math.floor(seconds / 60);
    return `Confirmed ${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }

  function setConnection(online, label = online ? "Panel online" : "Panel offline") {
    elements.connection.classList.toggle("online", online);
    elements.connection.classList.toggle("offline", !online);
    elements.connectionLabel.textContent = label;
  }

  function renderMode(mode, updatedAt, pending = false) {
    const safeMode = labels[mode] ? mode : "unknown";
    const meta = labels[safeMode];
    currentMode = safeMode;
    elements.modeLabel.textContent = pending ? `Switching to ${meta.title.toLowerCase()}…` : meta.title;
    elements.modeDescription.textContent = pending
      ? (safeMode === "away" ? "HomeBase exit delay is running" : "HomeBase is applying the mode")
      : meta.description;
    elements.confirmed.textContent = pending ? "Command accepted; waiting for HomeBase" : relativeTime(updatedAt);
    elements.shield.className = `shield ${safeMode}`;
    elements.shieldGlyph.setAttribute("d", meta.glyph);
    elements.buttons.forEach((button) => {
      button.classList.toggle("selected", button.dataset.mode === safeMode);
    });
  }

  function showMessage(text = "", kind = "") {
    elements.message.textContent = text;
    elements.message.className = `message ${kind}`.trim();
  }

  function setBusy(value) {
    busy = value;
    elements.buttons.forEach((button) => { button.disabled = value; });
    elements.refresh.disabled = value;
    elements.shield.classList.toggle("busy", value);
  }

  async function readJson(response) {
    try { return await response.json(); }
    catch { return { ok: false, error: "The local panel returned an invalid response" }; }
  }

  async function refreshStatus({ quiet = false } = {}) {
    if (busy) return;
    if (!quiet) showMessage("Checking current mode…");
    try {
      const response = await fetch(apiUrl("api/status"), {
        credentials: "same-origin",
        cache: "no-store",
      });
      const data = await readJson(response);
      if (data.csrf) csrf = data.csrf;
      elements.provider.textContent = data.provider || "Local panel";
      elements.demoBanner.hidden = data.live !== false;
      if (!response.ok || !data.ok) throw new Error(data.error || "Unable to read security mode");
      renderMode(data.mode, data.updated_at, Boolean(data.pending));
      setConnection(Boolean(data.connected), data.connected ? "Panel online" : "Provider offline");
      if (!quiet) showMessage("Status confirmed", "success");
    } catch (error) {
      setConnection(false);
      elements.confirmed.textContent = "Not confirmed";
      showMessage(error.message || "Unable to contact the panel", "error");
    }
  }

  async function setMode(mode) {
    if (busy) return;
    setBusy(true);
    showMessage(`Requesting ${labels[mode].title.toLowerCase()} mode…`);
    try {
      const response = await fetch(apiUrl("api/mode"), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ mode }),
      });
      const data = await readJson(response);
      if (!response.ok || !data.ok) {
        const error = new Error(data.error || "The mode change failed");
        error.status = response.status;
        throw error;
      }
      renderMode(data.mode, data.updated_at, Boolean(data.pending));
      setConnection(Boolean(data.connected));
      showMessage(
        data.pending
          ? `${labels[data.mode]?.title || "Mode"} requested—waiting for HomeBase`
          : `${labels[data.mode]?.title || "Mode"} confirmed`,
        "success",
      );
      if (data.pending) window.setTimeout(() => refreshStatus({ quiet: true }), 2000);
    } catch (error) {
      showMessage(error.message || "The mode change failed", "error");
      if (error.status === 403) await refreshStatus({ quiet: true });
    } finally {
      setBusy(false);
    }
  }

  elements.buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.mode;
      if (mode !== currentMode) setMode(mode);
      else showMessage(`${labels[mode].title} is already active`);
    });
  });
  elements.refresh.addEventListener("click", () => refreshStatus());

  refreshStatus();
  window.setInterval(() => refreshStatus({ quiet: true }), 15000);
})();
