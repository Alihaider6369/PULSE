const API = "/api/settings";

function showMessage(text, ok) {
  const el = document.getElementById("message");
  el.textContent = text;
  el.style.color = ok ? "#10b981" : "#ef4444";
}

async function loadSettings() {
  try {
    const fetchFunc = window.Auth ? window.Auth.authFetch.bind(window.Auth) : fetch;
    const res = await fetchFunc(API);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();
    document.getElementById("threshold").value = s.poor_posture_threshold_seconds;
    document.getElementById("cooldown").value = s.cooldown_seconds;
    document.getElementById("warning-duration").value = s.warning_duration_seconds;
    document.getElementById("min-confidence").value = s.min_confidence;
    document.getElementById("sound").checked = s.sound_enabled;
  } catch (err) {
    console.error("Settings load failed:", err);
    showMessage("Could not load settings", false);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    poor_posture_threshold_seconds: parseFloat(document.getElementById("threshold").value),
    cooldown_seconds: parseFloat(document.getElementById("cooldown").value),
    warning_duration_seconds: parseFloat(document.getElementById("warning-duration").value),
    min_confidence: parseFloat(document.getElementById("min-confidence").value),
    sound_enabled: document.getElementById("sound").checked,
  };

  try {
    const fetchFunc = window.Auth ? window.Auth.authFetch.bind(window.Auth) : fetch;
    const res = await fetchFunc(API, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showMessage("Saved successfully", true);
  } catch (err) {
    console.error("Settings save failed:", err);
    showMessage("Could not save. Check the values.", false);
  }
}

document.getElementById("settings-form").addEventListener("submit", saveSettings);
loadSettings();