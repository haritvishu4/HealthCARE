/** Existing page markup. Styling is in ../css/styles.css. */
function render() {
  let steps = ["Identify", "Converse", "Documents", "Summary", "Consult"];
  const dashboard = state.view === "dashboard";
  const doctorAccess = typeof backend !== "undefined" && backend.config?.role === "doctor";
  document.querySelector("#app").innerHTML =
    `<div class="shell"><aside class="sidebar"><div class="brand"><span class="brandmark">+</span><span>care<span style="color:#7cae94">.</span></span></div><div class="label">WORKSPACE</div><nav>${[
      ...(doctorAccess ? [["dashboard", "grid", "Doctor dashboard"]] : []),
      ["intake", "heart", "Patient intake"],
      ["records", "file", "Medical records"],
      ["history", "clock", "Visit history"],
      ...(doctorAccess ? [["doctor", "doctor", "Physician console"]] : []),
    ]
      .map(
        ([v, i, t]) =>
          `<button class="nav ${state.view === v ? "active" : ""}" data-view="${v}" title="${t}">${icon(i)}<span>${t}</span>${v === "intake" ? '<b class="badge">1</b>' : ""}</button>`,
      )
      .join(
        "",
      )}</nav><div class="sidebottom"><div class="help">${icon("shield")} &nbsp; A little help, a lot of care.<p>You can pause or ask a staff member for help at any time.</p><button id="help">How this works ${icon("arrow")}</button></div><div class="profile"><div class="avatar">OP</div><div>Outpatient desk<small>Demo workspace</small></div></div></div></aside><div><header class="topbar"><div class="crumb">Workspace &nbsp; / &nbsp; <b>${dashboard ? "Doctor dashboard" : state.view === "intake" ? "Patient intake" : state.view === "doctor" ? "Physician console" : state.view === "records" ? "Medical records" : "Visit history"}</b></div><div class="tools"><button id="audio" aria-pressed="${state.audio}">${icon("sound")} <span class="tooltext">Audio ${state.audio ? "on" : "off"}</span></button><button id="size" title="Toggle large text">A<span style="font-size:17px">a</span></button><button id="contrast" title="Toggle high contrast">◐</button><select id="language" aria-label="Voice language"><option value="en-IN" ${state.lang === "en-IN" ? "selected" : ""}>English voice</option><option value="hi-IN" ${state.lang === "hi-IN" ? "selected" : ""}>Hindi voice</option></select><span class="demo">UI PROTOTYPE</span></div></header><main class="main"><div class="intro"><div><h1>${dashboard ? "Your doctor dashboard." : state.view === "intake" ? "A better start to your care." : state.view === "doctor" ? "Ready for your review." : state.view === "records" ? "Your records, together." : "Every visit, in context."}</h1><p>${dashboard ? "Every consultation, with the context you need." : state.view === "intake" ? "Tell us your story. We’ll help your doctor see the whole picture." : "Patient-reported information, ready to review."}</p></div><button class="outline" id="new">${icon("plus")} New intake</button></div>${state.view === "intake" ? `<div class="journey" aria-label="Patient journey">${steps.map((s, i) => `<button class="step ${i === state.step ? "active" : i < state.step ? "done" : ""}" data-step="${i}"><span class="num">${i < state.step ? "✓" : i + 1}</span><span><strong>${s}</strong><small>${["Profile & consent", "Your health story", "Upload & review", "Check your details", "Doctor review"][i]}</small></span></button>`).join("")}</div><div class="layout"><section class="card">${mainCard()}</section>${aside()}</div>` : otherView()}<footer class="footer"><span>${icon("shield")} &nbsp;AI-assisted draft · Physician approval required</span><span>Your story matters. Your doctor stays in control.</span></footer></main></div></div>`;
  bind();
}
function mainCard() {
  let titles = [
    "Let’s get to know you",
    "Let’s talk about your health",
    "Bring your records together",
    "Review your health story",
    "You’re ready for consultation",
  ];
  return `<div class="cardhead"><div><h2>${titles[state.step]}</h2><p>${["Confirm your profile and choose what to share.", "A few simple questions, one at a time.", "Add context from previous visits.", "Check the details before sharing with your doctor.", "Your doctor will review your reported history."][state.step]}</p></div><span class="pill">${state.step === 1 ? `Question ${state.q + 1} of 5` : ["Profile", "", "Optional", "Draft summary", "Draft saved"][state.step]}</span></div><div class="patient"><div class="avatar">${esc(
    state.name
      .split(" ")
      .map((s) => s[0])
      .join("")
      .slice(0, 2),
  )}</div><div><strong>${esc(state.name)}</strong><small>${esc(state.age)} years · ${esc(state.sex)} &nbsp; | &nbsp; Demo patient</small></div><button id="editprofile">Edit profile</button></div><div class="interview">${[identify, converse, documents, summary, consult][state.step]()}</div>${state.step < 4 ? `<div class="cardfoot"><button class="back" id="back">← &nbsp; ${state.step === 1 && state.q === 0 ? "Profile" : "Back"}</button><span style="font-size:12px;color:var(--muted)">${state.step === 1 ? "Take your time. There’s no rush." : ""}</span><button class="primary" id="next">${state.step === 0 ? "Start interview" : state.step === 2 ? "Review summary" : state.step === 3 ? "Share with doctor" : "Continue"} ${icon("arrow")}</button></div>` : ""}`;
}
function identify() {
  return `<span class="eyebrow">PATIENT PROFILE</span><div class="formrow"><label class="field">Full name<input id="name" class="textinput" value="${esc(state.name)}"></label><label class="field">Age<input id="age" type="number" min="1" max="120" class="textinput" value="${esc(state.age)}"></label></div><div class="formrow"><label class="field">Sex<select id="sex" class="textinput">${["Male", "Female", "Other", "Prefer not to say"].map((x) => `<option ${x === state.sex ? "selected" : ""}>${x}</option>`)}</select></label><label class="field">Interview type<select id="mode" class="textinput"><option ${state.mode === "General" ? "selected" : ""}>General</option><option ${state.mode === "AYUSH" ? "selected" : ""}>AYUSH</option></select></label></div><div class="notice">Demo patient access. ABHA verification and patient login are not connected.</div><label class="consent"><input id="consent" type="checkbox" ${state.consent ? "checked" : ""}>I agree to use my answers to prepare a draft history for this demo visit.</label><label class="consent"><input id="share" type="checkbox" ${state.share ? "checked" : ""}>Share my draft with the physician console. I can revoke this before submission.</label>`;
}
function converse() {
  return `<div class="eyebrow"><span class="spark">${icon("spark")}</span> YOUR HEALTH STORY <span style="margin-left:auto;color:#93a198;font-size:10px">${state.mode.toUpperCase()} INTAKE</span></div><h2 class="question">${q().title}</h2><p class="sub">${q().sub}</p><div class="options">${q()
    .options.map(
      (x) =>
        `<button class="option ${state.choice === x ? "selected" : ""}" data-answer="${esc(x)}"><span class="radio"></span>${x}</button>`,
    )
    .join(
      "",
    )}</div><input class="textinput" id="custom" placeholder="Or describe it in your own words…" aria-label="Your answer" value="${esc(state.custom)}"><div class="voice"><button class="mic" id="mic" title="Speak your answer">${icon("mic")}</button><div><strong>Prefer to say it?</strong><small>Tap the mic and speak in ${state.lang === "hi-IN" ? "Hindi" : "English"}.</small></div><div class="wave">${"<i></i>".repeat(17)}</div></div>${state.choice === "Chest pain with difficulty breathing" ? '<div class="alert">Please seek immediate help from hospital staff. This application cannot contact triage or emergency services.</div>' : ""}`;
}
function documents() {
  return `<p class="sub">Prescriptions, lab reports, and discharge summaries.</p><div class="upload">${icon("upload")}<p>Add a medical document</p><input id="upload" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple aria-label="Choose medical documents"><p style="font-size:12px;color:var(--muted)">PDF, JPG or PNG · Files stay in this browser session</p></div>${state.files.map((f) => `<div class="record"><div>${icon("file")} &nbsp;${esc(f.name)}<small>Added locally · Extraction not connected</small></div><button data-remove="${esc(f.id || f.name)}" aria-label="Remove ${esc(f.name)}">×</button></div>`).join("")}<div class="notice">OCR and clinical extraction need a backend connection. This demo does not analyze uploaded documents.</div><p class="sub">No documents with you? Continue without uploading.</p>`;
}
function fields() {
  let a = state.answers;
  return {
    "Chief complaint": a[0] || "Not yet reported",
    "History of present illness": a.length
      ? `${a[1] || "Onset not reported"}. Impact: ${a[2] || "Not reported"}. Other symptoms: ${a[3] || "Not reported"}.`
      : "Not yet reported",
    "Past medical / surgical history": "Not collected in this demo",
    "Drug & allergy history": a[4] || "Not yet reported",
    "Family / personal history": "Not collected in this demo",
    "Review of systems": "Incomplete — clinician review needed",
    "Prior investigations": state.files.length
      ? `${state.files.length} document(s) added. Contents have not been extracted.`
      : "No documents supplied",
  };
}
function summary() {
  if (!Object.keys(state.summary).length) state.summary = fields();
  return `<span class="pill">Patient-reported draft · Not a diagnosis</span><div class="summary">${Object.entries(
    state.summary,
  )
    .map(
      ([k, v]) =>
        `<label>${esc(k)}<textarea class="textinput" data-summary="${esc(k)}">${esc(v)}</textarea></label>`,
    )
    .join(
      "",
    )}</div><label class="consent"><input id="share" type="checkbox" ${state.share ? "checked" : ""}>I agree to share this draft with the physician console.</label><button class="outline" id="readsummary">${icon("sound")} Read draft aloud</button>`;
}
function consult() {
  const doctorAccess = typeof backend !== "undefined" && backend.config?.role === "doctor";
  return `<div class="empty"><div style="color:var(--green);font-size:40px">✓</div><h2>History prepared.</h2><p class="sub">${doctorAccess ? "Your draft is available in the physician console.<br>A doctor can review, amend, accept, or reject it." : "Your draft has been saved for your doctor to review."}</p>${doctorAccess ? `<button class="primary" data-view="doctor">Open physician console ${icon("arrow")}</button>` : ""}</div><div class="notice">Draft saved only. Nothing has been sent to a hospital, ABHA account, or healthcare professional.</div><button class="outline" id="end">End session & clear details</button>`;
}
function aside() {
  return `<aside class="aside"><div class="card sidecard"><h3>${icon("file")} Patient context <span class="pill" style="margin-left:auto;font-size:9px">REPORTED</span></h3><div class="contextitem"><small>VISIT TYPE</small><strong>${state.mode} outpatient consultation</strong></div><div class="contextitem"><small>PAST CONDITIONS</small><div class="chips"><span class="chip">Not provided</span></div></div><div class="contextitem"><small>KNOWN ALLERGIES</small><div class="chips"><span class="chip amber">Not confirmed</span></div></div><div class="sectionline"></div><button class="editlink" data-view="records">View medical records &nbsp; ↗</button></div><div class="card sidecard"><h3>Your intake progress</h3><div style="display:flex;justify-content:space-between;font-size:12px;color:var(--muted)"><span>Building your health story</span><b style="color:var(--green)">${Math.round(((state.step === 1 ? 1 + state.q / 5 : state.step) / 4) * 100)}%</b></div><div class="progressline"><span style="width:${((state.step === 1 ? 1 + state.q / 5 : state.step) / 4) * 100}%"></span></div>${["Profile & consent", "Symptoms & health history", "Medical documents", "Ready for your doctor"].map((t, i) => `<div class="checkrow ${i < state.step ? "complete" : ""}"><span>${i < state.step ? "✓" : "○"}</span>${t}</div>`).join("")}</div><div class="note">${icon("shield")} &nbsp; <strong>You’re in control.</strong><p>Review your answers before sharing. Your doctor makes all clinical decisions.</p><button class="editlink" style="margin-top:12px" id="privacy">Manage consent →</button></div></aside>`;
}
function otherView() {
  if (state.view === "records")
    return `<section class="card"><div class="cardhead"><h2>Medical documents</h2><button class="outline" id="adddocs">${icon("plus")} Add document</button></div><div class="interview">${state.files.length ? state.files.map((f) => `<div class="record"><div>${icon("file")} ${esc(f.name)}<small>This session · Awaiting extraction</small></div><span class="pill">Local file</span></div>`).join("") : '<div class="empty">' + icon("file") + '<h2>No records added yet</h2><p class="sub">Add previous medical documents during your intake.</p></div>'}</div></section>`;
  if (state.view === "history")
    return `<section class="card"><div class="cardhead"><h2>Visit history</h2><span class="pill">Current session</span></div><div class="interview">${state.submitted ? `<div class="record"><div>${esc(state.name)} · ${state.mode} consultation<small>${new Date().toLocaleDateString("en-IN")} · Draft shared in demo</small></div><button class="outline" data-view="doctor">View draft</button></div>` : '<div class="empty"><h2>No completed visits</h2><p class="sub">Your current intake will appear here after you share the draft.</p></div>'}</div></section>`;
  return `<section class="card"><div class="cardhead"><div><h2>${state.submitted ? esc(state.name) + " · History review" : "Physician console"}</h2><p>Clinical review remains with the physician.</p></div><span class="pill">${state.review || "Awaiting review"}</span></div><div class="interview">${state.submitted ? summary() + `<div class="cardfoot" style="padding:20px 0"><button class="outline" id="reject">Reject draft</button><button class="primary" id="accept">Accept reviewed draft ${icon("check")}</button></div>` : '<div class="empty"><h2>No draft shared yet</h2><p class="sub">Complete the patient intake and share the summary to review it here.</p><button class="primary" data-view="intake">Return to intake</button></div>'}</div></section>`;
}
