/** Doctor overview. Counts and visit pages come from the scoped, authenticated API. */
const doctorDashboard = { status: "all", offset: 0, limit: 10, request: 0 };
const dashboardStatuses = {
  all: "All consultations", pending: "Awaiting review", reviewed: "Reviewed",
  draft: "Intake in progress", rejected: "Rejected",
};

function doctorDashboardView() {
  return `<section class="doctor-dashboard" aria-label="Doctor dashboard">
    <div class="doctor-welcome"><div><span class="doctor-eyebrow">YOUR CLINICAL WORKSPACE</span><h2>A clear view.<br>A thoughtful review.</h2><p>Patient stories, prepared drafts, and your next review — together in one place.</p></div><div class="doctor-welcome-side">${icon("doctor")}<span>${esc(new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" }))}</span><small>Care, with you at the centre.</small></div></div>
    <div id="doctor-dashboard-content" aria-live="polite" aria-busy="true"><div class="doctor-loading" role="status">Loading your consultations…</div></div>
  </section>`;
}

function dashboardDate(timestamp) {
  return new Date(timestamp * 1000).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function dashboardStatus(visit) {
  if (!visit.has_analysis) return "draft";
  return ["reviewed", "rejected"].includes(visit.status) ? visit.status : "pending";
}

function dashboardContents(data) {
  const cards = [
    ["all", "Total consultations", data.stats.total, "file", "Across your workspace"],
    ["pending", "Awaiting review", data.stats.pending, "clock", "Prepared drafts to review"],
    ["reviewed", "Reviewed", data.stats.reviewed, "check", "Your recorded reviews"],
    ["draft", "Intake in progress", data.stats.draft, "heart", "Analysis not yet prepared"],
  ];
  const rows = data.items.map((visit) => {
    const status = dashboardStatus(visit);
    const initials = visit.name.trim().split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    return `<tr><td><div class="doctor-patient"><span class="avatar">${esc(initials)}</span><div><strong>${esc(visit.name)}</strong><small>${esc(visit.age)} years · ${esc(visit.gender)}</small></div></div></td><td class="doctor-mode">${esc(visit.mode)}</td><td class="doctor-updated">${esc(dashboardDate(visit.updated_at))}</td><td><span class="doctor-status doctor-status-${status}"><span aria-hidden="true"></span>${dashboardStatuses[status]}</span></td><td><button class="doctor-open" data-doctor-open="${esc(visit.id)}" aria-label="Open consultation for ${esc(visit.name)}">${visit.has_analysis ? "Review" : "View intake"} ${icon("arrow")}</button></td></tr>`;
  }).join("");
  const empty = data.stats.total === 0;
  return `<div class="doctor-metrics">${cards.map(([filter, label, value, symbol, hint]) => `<button class="doctor-metric ${filter === doctorDashboard.status ? "is-selected" : ""}" data-doctor-filter="${filter}" aria-pressed="${filter === doctorDashboard.status}"><span class="doctor-metric-top">${label}<span>${icon(symbol)}</span></span><strong>${value}</strong><small>${hint}</small></button>`).join("")}</div>
    <div class="doctor-columns"><section class="card doctor-queue" aria-labelledby="doctor-queue-title"><div class="cardhead"><div><h2 id="doctor-queue-title">Consultation queue</h2><p>Most recently updated first</p></div><button class="outline doctor-refresh" id="doctor-refresh">Refresh</button></div>
    <div class="doctor-filters" role="group" aria-label="Filter consultations">${Object.entries(dashboardStatuses).map(([key, label]) => `<button data-doctor-filter="${key}" class="${key === doctorDashboard.status ? "active" : ""}" aria-pressed="${key === doctorDashboard.status}">${label}</button>`).join("")}</div>
    ${rows ? `<div class="doctor-table-wrap"><table class="doctor-table"><caption class="doctor-sr-only">${dashboardStatuses[doctorDashboard.status]}</caption><thead><tr><th scope="col">Patient</th><th scope="col">Visit type</th><th scope="col">Last updated</th><th scope="col">Status</th><th scope="col"><span class="doctor-sr-only">Action</span></th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="doctor-empty">${icon(empty ? "heart" : "check")}<h3>${empty ? "Your next consultation starts here." : "No consultations in this view."}</h3><p>${empty ? "Saved patient intakes and drafts shared with you will appear here." : "Choose another status to see more consultations."}</p><button class="outline" ${empty ? 'id="doctor-start-intake"' : 'data-doctor-filter="all"'}>${empty ? "Go to patient intake" : "View all consultations"} ${icon("arrow")}</button></div>`}
    <div class="doctor-pagination"><span>${data.total_matches ? `${data.offset + 1}–${data.offset + data.items.length} of ${data.total_matches}` : "0 consultations"}</span><div><button class="outline" id="doctor-previous" data-unavailable="${data.offset === 0}" ${data.offset === 0 ? "disabled" : ""}>Previous</button><button class="outline" id="doctor-next" data-unavailable="${!data.has_more}" ${!data.has_more ? "disabled" : ""}>Next ${icon("arrow")}</button></div></div></section>
    <aside class="doctor-aside"><section class="card doctor-checklist"><span class="doctor-eyebrow">A MOMENT BEFORE YOU REVIEW</span><h3>The whole story matters.</h3><ol><li><strong>Read the patient's story</strong><p>Open the consultation and review the reported history.</p></li><li><strong>Check the supporting details</strong><p>Verify extracted records and AI-assisted draft information.</p></li><li><strong>Add your review</strong><p>Amend the summary, add notes, and record your decision.</p></li></ol><div class="doctor-draft-note">${icon("shield")}<span>AI assists. Your clinical judgment leads.</span></div></section><p class="doctor-scope-note">Only consultations you own or that have been shared with you are shown. Counts include all saved visits in your workspace.</p></aside></div>`;
}

async function loadDoctorDashboard() {
  const target = document.getElementById("doctor-dashboard-content");
  if (!target) return;
  const request = ++doctorDashboard.request;
  target.setAttribute("aria-busy", "true");
  target.innerHTML = '<div class="doctor-loading" role="status">Loading your consultations…</div>';
  try {
    const data = await CareAPI.json(`/api/doctor/dashboard?status=${doctorDashboard.status}&offset=${doctorDashboard.offset}&limit=${doctorDashboard.limit}`);
    if (!target.isConnected || request !== doctorDashboard.request) return;
    // A review elsewhere can remove the final row on the selected page.
    if (data.offset > 0 && !data.items.length) {
      doctorDashboard.offset = 0;
      return await loadDoctorDashboard();
    }
    target.innerHTML = dashboardContents(data);
    target.querySelectorAll("[data-doctor-filter]").forEach((button) => {
      button.onclick = () => {
        doctorDashboard.status = button.dataset.doctorFilter;
        doctorDashboard.offset = 0;
        void loadDoctorDashboard();
      };
    });
    target.querySelectorAll("[data-doctor-open]").forEach((button) => {
      button.onclick = () => work(() => loadConsultation(button.dataset.doctorOpen, "doctor"));
    });
    target.querySelector("#doctor-refresh").onclick = () => void loadDoctorDashboard();
    target.querySelector("#doctor-previous").onclick = () => {
      doctorDashboard.offset = Math.max(0, doctorDashboard.offset - doctorDashboard.limit);
      void loadDoctorDashboard();
    };
    target.querySelector("#doctor-next").onclick = () => {
      if (!data.has_more) return;
      doctorDashboard.offset += doctorDashboard.limit;
      void loadDoctorDashboard();
    };
    const start = target.querySelector("#doctor-start-intake");
    if (start) start.onclick = () => { state.view = "intake"; render(); };
  } catch (error) {
    if (!target.isConnected || request !== doctorDashboard.request) return;
    target.innerHTML = `<div class="doctor-empty"><h3>We couldn’t load your consultations.</h3><p role="alert">${esc(error.message)}</p><button class="outline" id="doctor-retry">Try again</button></div>`;
    target.querySelector("#doctor-retry").onclick = () => void loadDoctorDashboard();
  } finally {
    if (request === doctorDashboard.request) target.setAttribute("aria-busy", "false");
  }
}
