const API = "/api/sessions";
const ACCENT = "#6366f1";

function formatDuration(seconds) {
  const s = Math.round(seconds || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
}

function formatDate(iso) {
  return new Date(iso).toLocaleString();
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function scoreColor(score) {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

function scoreBadgeClass(score) {
  if (score >= 80) return "good";
  if (score >= 60) return "warn";
  return "poor";
}

function scoreTip(score) {
  if (score >= 80) return "Great job! You are sitting well most of the time.";
  if (score >= 60) return "Good effort. A few posture breaks will help you improve.";
  return "Try sitting upright more often. Small changes add up.";
}

function renderHero(sessions) {
  const scored = sessions.filter(s => s.awareness_score !== null);
  const el = document.getElementById("hero-score");
  if (!scored.length) {
    setText("hero-tip", "Start a monitoring session to see your score.");
    return;
  }
  const avg = scored.reduce((a, s) => a + s.awareness_score, 0) / scored.length;
  el.textContent = `${avg.toFixed(0)}%`;
  el.style.color = scoreColor(avg);
  setText("hero-tip", scoreTip(avg));
}

function renderCards(sessions) {
  const totalGood = sessions.reduce((a, s) => a + (s.good_seconds || 0), 0);
  const totalPoor = sessions.reduce((a, s) => a + (s.poor_seconds || 0), 0);
  const totalWarnings = sessions.reduce((a, s) => a + (s.warning_count || 0), 0);

  setText("total-sessions", sessions.length);
  setText("total-time", formatDuration(totalGood + totalPoor));
  setText("good-time", formatDuration(totalGood));
  setText("poor-time", formatDuration(totalPoor));
  setText("warnings", totalWarnings);
}

function renderTable(sessions) {
  const body = document.getElementById("sessions-body");
  body.innerHTML = "";
  sessions.slice(0, 10).forEach(s => {
    const row = document.createElement("tr");
    const score = s.awareness_score;
    const warnClass = s.warning_count > 0 ? "warn" : "good";
    const scoreCell = score === null
      ? `<span class="badge">-</span>`
      : `<span class="badge ${scoreBadgeClass(score)}">${score.toFixed(1)}%</span>`;

    row.innerHTML = `
      <td>${formatDate(s.started_at)}</td>
      <td>${formatDuration(s.duration_seconds)}</td>
      <td>${formatDuration(s.good_seconds)}</td>
      <td>${formatDuration(s.poor_seconds)}</td>
      <td><span class="badge ${warnClass}">${s.warning_count}</span></td>
      <td>${scoreCell}</td>`;
    body.appendChild(row);
  });
}

function renderChart(sessions) {
  // Box (bar) chart, one bar per session, colored by score
  const ordered = [...sessions].reverse().filter(s => s.awareness_score !== null);
  new Chart(document.getElementById("score-chart"), {
    type: "bar",
    data: {
      labels: ordered.map(s => formatDate(s.started_at)),
      datasets: [{
        label: "Awareness score (%)",
        data: ordered.map(s => s.awareness_score),
        backgroundColor: ordered.map(s => scoreColor(s.awareness_score)),
        borderRadius: 8,
        maxBarThickness: 48,
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: { min: 0, max: 100, ticks: { color: "#6b7280" }, grid: { color: "#f1f5f9" } },
        x: { ticks: { color: "#6b7280" }, grid: { display: false } },
      },
      plugins: { legend: { labels: { color: "#111827" } } },
    },
  });
}

async function loadDashboard() {
  const status = document.getElementById("status");
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sessions = await res.json();
    renderHero(sessions);
    renderCards(sessions);
    renderTable(sessions);
    renderChart(sessions);
  } catch (err) {
    console.error("Dashboard load failed:", err);
    status.textContent = "Offline";
    status.classList.add("offline");
  }
}

loadDashboard();