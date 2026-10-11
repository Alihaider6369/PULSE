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
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();

    if (!s.active) {
      el.textContent = "-";
      el.style.color = "";
      state.textContent = "Monitor is off";
      document.getElementById("live-tip").textContent = "Run python monitor\\monitor.py to start.";
    } else {
      el.textContent = POSTURE_TEXT[s.posture] || "Detecting...";
      el.style.color = s.posture === "good" ? "#10b981"
                     : s.posture === "poor_posture" ? "#ef4444" : "#f59e0b";
      state.textContent = "Monitor is running";
      document.getElementById("live-tip").textContent =
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

refresh();
setInterval(refresh, 2000);