const API = "/api/sessions";
let allSessions = [];

function formatDuration(seconds) {
  const s = Math.round(seconds || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
}

function formatDate(iso) {
  return new Date(iso).toLocaleString();
}

function scoreBadgeClass(score) {
  if (score >= 80) return "good";
  if (score >= 60) return "warn";
  return "poor";
}

function matchesFilter(s, filter) {
  if (filter === "all") return true;
  if (s.awareness_score === null) return false;
  if (filter === "good") return s.awareness_score >= 80;
  if (filter === "mid") return s.awareness_score >= 60 && s.awareness_score < 80;
  return s.awareness_score < 60;
}

function render() {
  const filter = document.getElementById("filter").value;
  const body = document.getElementById("history-body");
  const empty = document.getElementById("empty");
  const rows = allSessions.filter(s => matchesFilter(s, filter));

  body.innerHTML = "";
  empty.hidden = rows.length > 0;

  rows.forEach(s => {
    const score = s.awareness_score;
    const scoreCell = score === null
      ? `<span class="badge">-</span>`
      : `<span class="badge ${scoreBadgeClass(score)}">${score.toFixed(1)}%</span>`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatDate(s.started_at)}</td>
      <td>${formatDuration(s.duration_seconds)}</td>
      <td>${formatDuration(s.good_seconds)}</td>
      <td>${formatDuration(s.poor_seconds)}</td>
      <td><span class="badge ${s.warning_count > 0 ? "warn" : "good"}">${s.warning_count}</span></td>
      <td>${scoreCell}</td>`;
    body.appendChild(tr);
  });
}

async function loadHistory() {
  try {
    const fetchFunc = window.Auth ? window.Auth.authFetch.bind(window.Auth) : fetch;
    const res = await fetchFunc(API);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allSessions = await res.json();
    render();
  } catch (err) {
    console.error("History load failed:", err);
    document.getElementById("empty").textContent = "Could not load sessions.";
    document.getElementById("empty").hidden = false;
  }
}

document.getElementById("filter").addEventListener("change", render);
loadHistory();