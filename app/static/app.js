(() => {
  "use strict";

  const labels = {
    away: { title: "Away", description: "Full monitoring" },
    schedule: { title: "Schedule", description: "Following timetable" },
    unknown: { title: "Unknown", description: "Status unavailable" },
  };

  const elements = {
    clock: document.querySelector("#clock"),
    date: document.querySelector("#date"),
    connection: document.querySelector("#connection"),
    connectionLabel: document.querySelector("#connection-label"),
    weatherCard: document.querySelector("#weather-card"),
    weatherLocation: document.querySelector("#weather-location"),
    temperature: document.querySelector("#temperature"),
    weatherTitle: document.querySelector("#weather-title"),
    feelsLike: document.querySelector("#feels-like"),
    weatherIcon: document.querySelector("#weather-icon use"),
    weatherIconSvg: document.querySelector("#weather-icon"),
    rainBanner: document.querySelector("#rain-banner"),
    rainHeadline: document.querySelector("#rain-headline"),
    rainDetail: document.querySelector("#rain-detail"),
    highLow: document.querySelector("#high-low"),
    rainToday: document.querySelector("#rain-today"),
    windSpeed: document.querySelector("#wind-speed"),
    weatherSetup: document.querySelector("#weather-setup"),
    demoBanner: document.querySelector("#demo-banner"),
    modeStatus: document.querySelector("#mode-status"),
    modeLabel: document.querySelector("#mode-label"),
    modeDescription: document.querySelector("#mode-description"),
    message: document.querySelector("#message"),
    buttons: [...document.querySelectorAll(".mode-button")],
    refresh: document.querySelector("#refresh"),
  };

  let csrf = "";
  let currentMode = "unknown";
  let busy = false;

  const apiUrl = (path) => new URL(path, window.location.href).toString();
  const rounded = (value, suffix = "°") => Number.isFinite(Number(value)) ? `${Math.round(Number(value))}${suffix}` : `--${suffix}`;

  function updateClock() {
    const now = new Date();
    elements.clock.textContent = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(now);
    elements.clock.dateTime = now.toISOString();
    elements.date.textContent = new Intl.DateTimeFormat(undefined, {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(now);
  }

  function setConnection(online, label = online ? "HomeBase online" : "HomeBase offline") {
    elements.connection.classList.toggle("online", online);
    elements.connection.classList.toggle("offline", !online);
    elements.connectionLabel.textContent = label;
  }

  function renderMode(mode, pending = false, activeMode = "") {
    const safeMode = labels[mode] ? mode : "unknown";
    const meta = labels[safeMode];
    const hasActiveRule = safeMode === "schedule" && activeMode && activeMode !== "Unknown";
    currentMode = safeMode;
    elements.modeLabel.textContent = pending ? `Switching to ${meta.title.toLowerCase()}…` : meta.title;
    elements.modeDescription.textContent = pending
      ? "Waiting for HomeBase"
      : (hasActiveRule ? `Active now · ${activeMode}` : meta.description);
    elements.modeStatus.className = `mode-status ${safeMode}${pending ? " busy" : ""}`;
    elements.buttons.forEach((button) => {
      button.classList.toggle("selected", button.dataset.mode === safeMode);
    });
  }

  function renderWeather(data) {
    elements.weatherSetup.hidden = true;
    elements.weatherLocation.textContent = String(data.location || "Local weather").toUpperCase();
    elements.temperature.textContent = rounded(data.temperature);
    elements.weatherTitle.textContent = data.condition || "Conditions unavailable";
    elements.feelsLike.textContent = `Feels like ${rounded(data.feels_like)}`;

    let icon = data.icon || "unknown";
    if (!data.is_day && (icon === "clear" || icon === "partly-cloudy")) icon += "-night";
    const allowedIcons = new Set(["clear", "clear-night", "partly-cloudy", "partly-cloudy-night", "cloudy", "fog", "rain", "showers", "storm", "snow", "unknown"]);
    if (!allowedIcons.has(icon)) icon = "unknown";
    elements.weatherIcon.setAttribute("href", `#weather-${icon}`);
    elements.weatherIconSvg.setAttribute("aria-label", data.condition || "Weather conditions");

    const rain = data.rain || {};
    elements.rainHeadline.textContent = rain.headline || "Rain forecast unavailable";
    elements.rainDetail.textContent = rain.detail || "Try refreshing shortly";
    elements.rainBanner.className = `rain-banner ${["wet", "watch", "dry"].includes(rain.tone) ? rain.tone : ""}`.trim();
    elements.highLow.textContent = `${rounded(data.high)} / ${rounded(data.low)}`;
    elements.rainToday.textContent = rounded(data.daily_rain_probability, "%");
    elements.windSpeed.textContent = rounded(data.wind_speed, " km/h");
    elements.weatherCard.classList.toggle("stale", Boolean(data.stale));
  }

  function renderWeatherError(data) {
    if (data.configured === false) {
      elements.weatherSetup.hidden = false;
      return;
    }
    elements.weatherSetup.hidden = true;
    elements.weatherTitle.textContent = "Forecast unavailable";
    elements.feelsLike.textContent = "Will try again automatically";
    elements.rainHeadline.textContent = "Weather connection problem";
    elements.rainDetail.textContent = data.error || "The forecast service did not respond";
    elements.rainBanner.className = "rain-banner watch";
  }

  function showMessage(text = "", kind = "") {
    elements.message.textContent = text;
    elements.message.className = `message ${kind}`.trim();
  }

  function setBusy(value) {
    busy = value;
    elements.buttons.forEach((button) => { button.disabled = value; });
    elements.refresh.disabled = value;
    elements.modeStatus.classList.toggle("busy", value);
  }

  async function readJson(response) {
    try { return await response.json(); }
    catch { return { ok: false, error: "The local dashboard returned an invalid response" }; }
  }

  async function refreshSecurity({ quiet = false } = {}) {
    if (busy) return;
    if (!quiet) showMessage("Checking HomeBase…");
    try {
      const response = await fetch(apiUrl("api/status"), {
        credentials: "same-origin",
        cache: "no-store",
      });
      const data = await readJson(response);
      if (data.csrf) csrf = data.csrf;
      elements.demoBanner.hidden = data.live !== false;
      if (!response.ok || !data.ok) throw new Error(data.error || "Unable to read security mode");
      renderMode(data.mode, Boolean(data.pending), data.active_mode);
      setConnection(Boolean(data.connected), data.connected ? "HomeBase online" : "Provider offline");
      if (!quiet) showMessage("Status confirmed", "success");
    } catch (requestError) {
      setConnection(false);
      renderMode("unknown");
      showMessage(requestError.message || "Unable to contact the dashboard", "error");
    }
  }

  async function refreshWeather({ force = false } = {}) {
    try {
      const suffix = force ? "?refresh=1" : "";
      const response = await fetch(apiUrl(`api/weather${suffix}`), { cache: "no-store" });
      const data = await readJson(response);
      if (!response.ok || !data.ok) {
        renderWeatherError(data);
        return;
      }
      renderWeather(data);
    } catch (requestError) {
      renderWeatherError({ configured: true, error: requestError.message });
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
        const modeError = new Error(data.error || "The mode change failed");
        modeError.status = response.status;
        throw modeError;
      }
      renderMode(data.mode, Boolean(data.pending), data.active_mode);
      setConnection(Boolean(data.connected));
      showMessage(
        data.pending ? `${labels[data.mode]?.title || "Mode"} requested—waiting for HomeBase` : `${labels[data.mode]?.title || "Mode"} confirmed`,
        "success",
      );
      if (data.pending) window.setTimeout(() => refreshSecurity({ quiet: true }), 2000);
    } catch (modeError) {
      showMessage(modeError.message || "The mode change failed", "error");
      if (modeError.status === 403) await refreshSecurity({ quiet: true });
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

  elements.refresh.addEventListener("click", () => {
    refreshSecurity();
    refreshWeather({ force: true });
  });

  updateClock();
  window.setInterval(updateClock, 1000);
  refreshSecurity();
  refreshWeather();
  window.setInterval(() => refreshSecurity({ quiet: true }), 15000);
  window.setInterval(() => refreshWeather(), 10 * 60 * 1000);
})();
