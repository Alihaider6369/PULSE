const API = "/api/live/status";

function fmt(seconds) {
  const s = Math.round(seconds || 0);
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

const POSTURE_TEXT = {
  good: "Good posture",
  lean_left: "Leaning left",
  lean_right: "Leaning right",
  poor_posture: "Poor posture",
};

async function refresh() {
  const el = document.getElementById("live-posture");
  const state = document.getElementById("live-state");
  const tip = document.getElementById("live-tip");
  try {
    const fetchFunc = (window.Auth && typeof window.Auth.authFetch === "function")
      ? window.Auth.authFetch.bind(window.Auth)
      : fetch;
    const targetUrl = window.getPulseApiUrl ? window.getPulseApiUrl(API) : API;
    const res = await fetchFunc(targetUrl);

    if (!res.ok) {
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        el.textContent = "-";
        el.style.color = "";
        state.textContent = "Storage unconfigured";
        if (tip) tip.textContent = err.detail || "Configure Upstash Redis in your serverless environment.";
        return;
      }
      if (res.status === 502) {
        el.textContent = "-";
        el.style.color = "";
        state.textContent = "Storage error";
        if (tip) tip.textContent = "Unable to connect to shared live storage.";
        return;
      }
      throw new Error(`HTTP ${res.status}`);
    }

    const s = await res.json();

    if (!s.active) {
      el.textContent = "-";
      el.style.color = "";
      state.textContent = "Monitor is off";
      if (tip) tip.textContent = "Run desktop application or python monitor\\monitor.py to start.";
    } else {
      el.textContent = POSTURE_TEXT[s.posture] || "Detecting...";
      el.style.color = s.posture === "good" ? "#10b981"
                     : s.posture === "poor_posture" ? "#ef4444" : "#f59e0b";
      state.textContent = "Monitor is running";
      if (tip) tip.textContent =
        s.posture === "poor_posture" ? "Sit up straight and relax your shoulders." : "Keep it up.";
    }

    document.getElementById("live-warnings").textContent = s.warnings ?? 0;
    document.getElementById("live-good").textContent = fmt(s.good_seconds);
    document.getElementById("live-poor").textContent = fmt(s.poor_seconds);
    document.getElementById("live-session").textContent = s.session_id ?? "-";
  } catch (err) {
    console.error("Live status failed:", err);
    state.textContent = "Backend offline";
  }
}

const downloadUrl = window.PULSE_DOWNLOAD_URL || "https://github.com/Alihaider6369/PULSE/releases";
const liveDownloadBtn = document.getElementById("btn-live-download");
if (liveDownloadBtn) liveDownloadBtn.href = downloadUrl;

refresh();
setInterval(refresh, 2000);