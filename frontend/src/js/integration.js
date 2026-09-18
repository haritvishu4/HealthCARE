/** Connect the original UI's existing controls to the backend, preserving its theme and screens. */
const backend = {
  patientData: null,
  patientId: null,
  consultationId: null,
  version: null,
  analysisId: null,
  report: null,
  pdfUrl: null,
  busy: false,
  consent: false,
  config: null,
  baseSummary: {},
  recorder: null,
  stream: null,
  recordingTimer: null,
  epoch: 0,
};
const original = {
  render,
  bind,
  next,
  reset,
  fields,
  identify,
  documents,
  summary,
  consult,
  otherView,
  aside,
};
fields = function () {
  const value = original.fields();
  value["Past medical / surgical history"] =
    useful(state.summary["Past medical / surgical history"]) || "Not provided";
  value["Family / personal history"] =
    useful(state.summary["Family / personal history"]) || "Not provided";
  value["Prior investigations"] = state.files.length
    ? state.files
        .map((f) => `${f.name}:\n${f.text || "Extracted document saved."}`)
        .join("\n\n")
        .slice(0, 7000) +
      "\nReview the original documents to verify extraction."
    : "No documents supplied";
  return value;
};
const useful = (value) =>
  value &&
  !/^(Not (yet )?(provided|reported|collected|confirmed)|Incomplete)/i.test(
    value,
  )
    ? value
    : "";

function patientPayload() {
  let details = state.answers;
  const drugHistory =
    useful(state.summary["Drug & allergy history"]) || details[4] || "";
  return {
    ...backend.patientData,
    name: state.name.trim(),
    age: Number(state.age),
    gender: state.sex,
    symptoms:
      useful(state.summary["Chief complaint"]) ||
      (state.mode === "AYUSH"
        ? details.filter(Boolean).join("; ")
        : details[0] || ""),
    duration: state.mode === "General" ? details[1] || "" : "",
    medical_history: useful(state.summary["Past medical / surgical history"]),
    allergies: /^No medicines or allergies$/i.test(drugHistory)
      ? "Patient reports no known allergies"
      : backend.patientData?.allergies || "",
    current_medicines: /^No medicines or allergies$/i.test(drugHistory)
      ? "Patient reports no current medicines"
      : backend.patientData?.current_medicines || "",
    additional_details: {
      history_of_present_illness: useful(
        state.summary["History of present illness"],
      ),
      impact_or_energy: details[2] || "",
      other_symptoms_or_habits: details[3] || "",
      drug_and_allergy_history: drugHistory,
      family_and_personal_history: useful(
        state.summary["Family / personal history"],
      ),
      ...(state.mode === "AYUSH"
        ? { appetite: details[0] || "", sleep: details[1] || "" }
        : {}),
    },
    mode: state.mode,
  };
}

async function askConsent() {
  if (backend.consent) return true;
  const allowed = window.confirm(
    "Allow this consultation to use Gemini for clinical draft analysis, Sarvam for voice transcription, and OCR.space for scanned documents? Your submitted medical information will be sent to the selected providers. Final decisions remain with your doctor.",
  );
  if (!allowed)
    throw new Error(
      "Processing consent was not granted. Your answers remain on this screen.",
    );
  backend.consent = true;
}

async function saveIntake() {
  capture();
  if (!state.name.trim() || !state.age || +state.age < 1 || +state.age > 120)
    throw new Error(
      "Use Edit profile to enter a name and an age between 1 and 120.",
    );
  await askConsent();
  const result = await CareAPI.json("/api/patient/intake", {
    method: "POST",
    body: {
      patient: patientPayload(),
      patient_id: backend.patientId,
      consultation_id: backend.consultationId,
      expected_version: backend.version,
      consent: backend.consent,
    },
  });
  backend.patientId = result.patient_id;
  backend.consultationId = result.consultation_id;
  backend.version = result.version;
  return result;
}

function reportSummary(report) {
  const base = fields();
  return {
    ...base,
    "Clinical assistance summary": report.summary,
    "Symptom analysis": report.symptoms_analysis,
    "Possible concerns (unconfirmed)":
      report.possible_conditions.join("\n") ||
      "None listed; this does not rule out illness.",
    "Suggested review priority": report.severity.replaceAll("_", " "),
    "Investigations for doctor consideration":
      report.recommended_tests.join("\n") || "Physician to decide.",
    "General precautions": report.precautions.join("\n"),
    "Missing details / follow-up questions": [
      ...report.missing_details,
      ...report.follow_up_questions,
    ].join("\n"),
    "AI notes for doctor review": report.doctor_notes,
  };
}

function changesOnly() {
  return Object.fromEntries(
    Object.entries(state.summary).filter(
      ([key, value]) => backend.baseSummary[key] !== value,
    ),
  );
}

async function analyzeCurrent() {
  const result = await CareAPI.json("/api/ai/analyze", {
    method: "POST",
    body: {
      consultation_id: backend.consultationId,
      expected_version: backend.version,
    },
  });
  backend.version = result.version;
  backend.analysisId = result.analysis_id;
  backend.report = result;
  backend.baseSummary = reportSummary(result);
  state.summary = { ...backend.baseSummary };
  backend.pdfUrl = null;
  return result;
}

function setDisabled() {
  document
    .querySelector("#app")
    ?.setAttribute("aria-busy", String(backend.busy));
  document
    .querySelectorAll("#app button, #app input, #app select, #app textarea")
    .forEach((element) => {
      element.disabled =
        element.dataset.unavailable === "true" || backend.busy || (!!backend.recorder && element.id !== "mic");
    });
}

async function work(action) {
  if (backend.busy) return;
  backend.busy = true;
  setDisabled();
  try {
    await action();
  } catch (error) {
    toast(error.message || "The request could not be completed.");
  } finally {
    backend.busy = false;
    setDisabled();
  }
}

next = function () {
  return work(async () => {
    capture();
    if (state.step === 0) {
      if (!state.consent)
        throw new Error("Please grant consent to begin the consultation.");
      await saveIntake();
      state.step = 1;
    } else if (state.step === 1) {
      const answer = state.custom.trim() || state.choice;
      if (!answer)
        throw new Error("Select an answer or describe it in your words.");
      state.answers[state.q] = answer;
      delete state.summary["Chief complaint"];
      delete state.summary["History of present illness"];
      if (state.q === 4) {
        delete state.summary["Drug & allergy history"];
        if (backend.patientData) {
          backend.patientData.allergies = "";
          backend.patientData.current_medicines = "";
        }
      }
      await saveIntake();
      backend.analysisId = null;
      backend.pdfUrl = null;
      if (state.q < 4) {
        state.q++;
        state.choice = state.answers[state.q] || "";
        state.custom = "";
      } else state.step = 2;
    } else if (state.step === 2) {
      await saveIntake();
      await analyzeCurrent();
      state.step = 3;
    } else if (state.step === 3) {
      if (!state.share) throw new Error("Confirm sharing before continuing.");
      const amendments = changesOnly();
      // Save corrected clinical fields, then regenerate analysis from the current inputs.
      await saveIntake();
      await analyzeCurrent();
      state.summary = { ...state.summary, ...amendments };
      const saved = await CareAPI.json(
        `/api/consultation/${backend.consultationId}/summary`,
        {
          method: "PATCH",
          body: { expected_version: backend.version, summary: amendments },
        },
      );
      backend.version = saved.version;
      if (
        backend.config?.mode === "production" &&
        backend.config?.role !== "doctor"
      ) {
        const doctor = window.prompt(
          "Enter the Supabase user ID of the doctor you want to share this consultation with.",
        );
        if (!doctor?.trim())
          throw new Error("Enter a doctor ID to share the consultation.");
        const shared = await CareAPI.json(
          `/api/consultation/${backend.consultationId}/share`,
          {
            method: "POST",
            body: {
              expected_version: backend.version,
              doctor_id: doctor.trim(),
            },
          },
        );
        backend.version = shared.version;
      }
      const pdf = await CareAPI.json("/api/prescription/generate", {
        method: "POST",
        body: {
          consultation_id: backend.consultationId,
          analysis_id: backend.analysisId,
          expected_version: backend.version,
        },
      });
      backend.pdfUrl = pdf.pdf_url;
      state.submitted = true;
      state.step = 4;
    }
    render();
    if (state.audio && state.step === 1) say(q().title);
  });
};

identify = function () {
  return original
    .identify()
    .replace(
      "Demo patient access. ABHA verification and patient login are not connected.",
      "Patient details are saved with this consultation. ABHA is not connected.",
    )
    .replace("for this demo visit.", "for this visit.")
    .replace("demo physician console", "physician console");
};

documents = function () {
  return original
    .documents()
    .replace(
      "Files stay in this browser session",
      "Saved with your consultation · Up to 10 MB each",
    )
    .replaceAll(
      "Added locally · Extraction not connected",
      "Saved · Extracted text available for review",
    )
    .replace(
      "OCR and clinical extraction need a backend connection. This demo does not analyze uploaded documents.",
      "Extracted text is sent for draft analysis. OCR can misread medical text; your doctor must verify it.",
    );
};

summary = function () {
  const html = original.summary();
  if (state.view !== "intake" || !backend.analysisId) return html;
  return `<div class="notice"><strong>Your clinical draft is ready.</strong><p>Download the summary, assessment, and your edits as a PDF for physician review.</p><button class="primary" id="downloadpdf">${icon("file")} Download draft PDF</button></div>${html}`;
};

consult = function () {
  return (
    original
      .consult()
      .replaceAll("demo physician console", "physician console")
      .replace(
        "Draft saved only. Nothing has been sent to a hospital, ABHA account, or healthcare professional.",
        "Clinical assistance draft saved. Final medical decisions and prescriptions require physician approval.",
      )
      .replace("End session & clear details", "End session on this device") +
    `<button class="primary" id="downloadpdf">${icon("file")} Download draft PDF</button>`
  );
};

otherView = function () {
  if (state.view === "dashboard") return doctorDashboardView();
  if (state.view === "history")
    return `<section class="card"><div class="cardhead"><h2>Patient visit history</h2><span class="pill">Saved records</span></div><div class="interview" id="savedhistory"><p class="sub">Loading saved consultations…</p></div></section>`;
  const html = original.otherView();
  if (state.view === "records")
    return html
      .replaceAll(
        "This session · Awaiting extraction",
        "Stored with your consultation",
      )
      .replaceAll("Local file", "Saved");
  if (state.view === "doctor") {
    const back = `<button class="outline doctor-back" data-view="dashboard">← Back to doctor dashboard</button>`;
    if (backend.analysisId) {
      const notes = !("Doctor notes" in state.summary)
        ? `<section class="doctor-review-notes"><label for="doctor-notes">Doctor notes</label><textarea id="doctor-notes" class="textinput" aria-describedby="doctor-notes-help">${esc(state.doctorNotes || "")}</textarea><p id="doctor-notes-help">Saved when you accept or reject the draft.</p></section>`
        : "";
      const actions = '<div class="cardfoot" style="padding:20px 0">';
      return back + html.replace(actions, notes + actions) +
        `<div class="cardfoot"><button class="primary" id="downloadpdf">${icon("file")} Download draft PDF</button></div>`;
    }
    if (backend.patientData) return back + `<section class="card"><div class="cardhead"><div><h2>${esc(state.name)}</h2><p>${esc(state.age)} years · ${esc(state.sex)} · ${esc(state.mode)} consultation</p></div><span class="pill">Intake in progress</span></div><div class="interview"><h3>No draft ready for review</h3><p class="sub">This intake has not been analysed yet. Review actions become available once a draft is prepared.</p><div class="summary"><label>Reported symptoms</label><p>${esc(backend.patientData.symptoms || "Not reported")}</p><label>Medical history</label><p>${esc(backend.patientData.medical_history || "Not reported")}</p></div></div></section>`;
    return back + html;
  }
  return html;
};

render = function () {
  if (backend.config?.role !== "doctor" && ["dashboard", "doctor"].includes(state.view))
    state.view = "intake";
  original.render();
  if (backend.config?.role !== "doctor") {
    document.querySelector('.nav[data-view="dashboard"]')?.remove();
    document.querySelector('.nav[data-view="doctor"]')?.remove();
  }
  const language = document.querySelector("#language");
  if (language && backend.config) {
    for (const code of backend.config.speech_languages.filter(
      (c) => !["en-IN", "hi-IN"].includes(c),
    )) {
      const option = document.createElement("option");
      option.value = code;
      option.textContent =
        code === "unknown" ? "Auto-detect voice" : `${code} voice`;
      language.append(option);
    }
    language.value = state.lang;
  }
  const voice = document.querySelector(".voice small");
  if (voice)
    voice.textContent = `Tap the mic to record in ${state.lang === "unknown" ? "your language" : state.lang}.`;
  const badge = document.querySelector(".demo");
  if (badge)
    badge.textContent = backend.config ? "AI DRAFT WORKSPACE" : "BACKEND CHECK";
  const patient = document.querySelector(".patient small");
  if (patient && backend.patientId)
    patient.textContent = `${state.age} years · ${state.sex} | Patient ${backend.patientId.slice(0, 8)}`;
  const context = document.querySelectorAll(".contextitem .chip");
  if (context[0])
    context[0].textContent =
      useful(state.summary["Past medical / surgical history"]) ||
      "Not provided";
  if (context[1])
    context[1].textContent =
      backend.patientData?.allergies ||
      useful(state.summary["Drug & allergy history"]) ||
      state.answers[4] ||
      "Not confirmed";
  const user = window.CareAuth?.user;
  const profile = document.querySelector(".profile");
  if (profile && user) {
    const initials = user.name.trim().split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    profile.innerHTML = `<div class="avatar">${esc(initials)}</div><div class="workspace-user">${esc(user.name)}<small>${esc(user.email)}</small></div>`;
  }
  const tools = document.querySelector(".tools");
  if (tools && user) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = "workspace-logout";
    button.title = "Sign out of your workspace";
    button.setAttribute("aria-label", "Sign out");
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4H4v16h5m5-13 5 5-5 5M9 12h10"/></svg><span>Sign out</span>';
    button.onclick = async () => {
      button.disabled = true;
      try {
        await window.CareAuth.logout();
      } catch (error) {
        toast(error.message);
        button.disabled = false;
      }
    };
    tools.append(button);
  }
  setDisabled();
  if (state.view === "history") void loadHistory();
  if (state.view === "dashboard") void loadDoctorDashboard();
};

reset = function () {
  backend.epoch++;
  if (backend.recordingTimer) clearTimeout(backend.recordingTimer);
  backend.recorder = null;
  backend.stream?.getTracks().forEach((track) => track.stop());
  backend.stream = null;
  Object.assign(backend, {
    patientData: null,
    patientId: null,
    consultationId: null,
    version: null,
    analysisId: null,
    report: null,
    pdfUrl: null,
    consent: false,
    baseSummary: {},
  });
  original.reset();
  toast(
    "Device session cleared. Previously saved records remain in visit history.",
  );
};

async function loadHistory() {
  const target = document.querySelector("#savedhistory");
  if (!target) return;
  try {
    const page = await CareAPI.json("/api/consultations?limit=25");
    const groups = page.items;
    if (!target.isConnected) return;
    groups.sort((a, b) => b.created_at - a.created_at);
    target.innerHTML = groups.length
      ? groups
          .map(
            (c) =>
              `<div class="record"><div>${esc(c.name)}<small>${new Date(c.created_at * 1000).toLocaleString()} · ${esc(c.status)}</small></div><button class="outline" data-load-consultation="${esc(c.id)}">Open</button></div>`,
          )
          .join("")
      : '<p class="sub">No saved visits yet. Begin an intake to create one.</p>';
    if (page.has_more) {
      const more = document.createElement("button");
      more.className = "outline";
      more.textContent = "Load more visits";
      more.onclick = () =>
        work(async () => {
          const result = await CareAPI.json(
            `/api/consultations?limit=25&offset=${groups.length}`,
          );
          groups.push(...result.items);
          for (const c of result.items) {
            const row = document.createElement("div");
            row.className = "record";
            row.innerHTML = `<div>${esc(c.name)}<small>${new Date(c.created_at * 1000).toLocaleString()} · ${esc(c.status)}</small></div><button class="outline">Open</button>`;
            row.querySelector("button").onclick = () =>
              work(() => loadConsultation(c.id));
            target.insertBefore(row, more);
          }
          if (!result.has_more) more.remove();
        });
      target.append(more);
    }
    target
      .querySelectorAll("[data-load-consultation]")
      .forEach(
        (button) =>
          (button.onclick = () =>
            work(() => loadConsultation(button.dataset.loadConsultation))),
      );
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}

async function loadConsultation(id, destination) {
  const c = await CareAPI.json(`/api/consultation/${id}`);
  backend.patientData = c.patient;
  backend.consultationId = c.id;
  backend.patientId = c.patient_id;
  backend.version = c.version;
  backend.consent = c.consent;
  backend.analysisId = c.analysis_id || null;
  backend.report = c.ai_analysis;
  backend.pdfUrl = null;
  Object.assign(state, {
    name: c.patient.name,
    age: String(c.patient.age),
    sex: c.patient.gender,
    mode: c.patient.mode,
    answers: [
      c.patient.mode === "AYUSH"
        ? c.patient.additional_details.appetite
        : c.patient.symptoms,
      c.patient.mode === "AYUSH"
        ? c.patient.additional_details.sleep
        : c.patient.duration,
      c.patient.additional_details.impact_or_energy,
      c.patient.additional_details.other_symptoms_or_habits,
      c.patient.additional_details.drug_and_allergy_history,
    ],
    files: c.documents.map((d) => ({
      id: d.id,
      name: d.name,
      size: d.size,
      text: d.text,
    })),
    choice: "",
    custom: "",
    submitted: !!c.analysis_id,
    summary: {
      "Past medical / surgical history":
        c.patient.medical_history || "Not provided",
      "Family / personal history":
        c.patient.additional_details.family_and_personal_history ||
        "Not provided",
    },
    consent: c.consent,
    share: true,
    q: 0,
    view: destination || (
      backend.config?.role === "doctor" && c.owner_id !== backend.config?.actor
        ? "doctor"
        : "intake"),
    step: c.analysis_id ? 3 : 1,
    review: c.status,
    doctorNotes: c.review?.doctor_notes || "",
  });
  if (c.ai_analysis) {
    backend.baseSummary = reportSummary(c.ai_analysis);
    state.summary = { ...backend.baseSummary, ...c.human_summary };
  } else {
    backend.baseSummary = {};
    state.summary = {
      "Past medical / surgical history":
        c.patient.medical_history || "Not provided",
    };
  }
  render();
}

async function downloadDraft() {
  capture();
  if (!backend.analysisId)
    throw new Error("Complete the intake analysis before downloading a PDF.");
  const saved = await CareAPI.json(
    `/api/consultation/${backend.consultationId}/summary`,
    {
      method: "PATCH",
      body: { expected_version: backend.version, summary: changesOnly() },
    },
  );
  backend.version = saved.version;
  const pdf = await CareAPI.json("/api/prescription/generate", {
    method: "POST",
    body: {
      consultation_id: backend.consultationId,
      analysis_id: backend.analysisId,
      expected_version: backend.version,
    },
  });
  backend.pdfUrl = pdf.pdf_url;
  await CareAPI.download(pdf.pdf_url, "Care-Clinical-Draft.pdf");
}

async function recordAudio() {
  if (backend.recorder && backend.recorder.state === "recording") {
    backend.recorder.stop();
    return;
  }
  await work(async () => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
      throw new Error(
        "Recording is unavailable here. Use Chrome/Safari on localhost, or type your answer.",
      );
    await saveIntake();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    backend.stream = stream;
    const type = [
      "audio/webm;codecs=opus",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ].find((t) => MediaRecorder.isTypeSupported(t));
    const recorder = type
      ? new MediaRecorder(stream, { mimeType: type })
      : new MediaRecorder(stream);
    const chunks = [];
    const epoch = backend.epoch;
    backend.recorder = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    recorder.onstop = () => {
      clearTimeout(backend.recordingTimer);
      stream.getTracks().forEach((track) => track.stop());
      backend.recorder = null;
      backend.stream = null;
      if (epoch !== backend.epoch) return;
      void work(async () => {
        const blob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        const form = new FormData();
        form.set("consultation_id", backend.consultationId);
        form.set("expected_version", String(backend.version));
        form.set("language", state.lang || "unknown");
        form.set(
          "file",
          blob,
          recorder.mimeType.includes("mp4") ? "speech.m4a" : "speech.webm",
        );
        const result = await CareAPI.json("/api/audio/transcribe", {
          method: "POST",
          body: form,
        });
        backend.version = result.version;
        backend.analysisId = null;
        backend.pdfUrl = null;
        state.custom = result.text;
        state.choice = "";
        render();
        toast("Transcript ready. Check it before continuing.");
      });
    };
    recorder.onerror = () => {
      stream.getTracks().forEach((track) => track.stop());
      backend.recorder = null;
      backend.stream = null;
      setDisabled();
      toast("Recording failed. You can type your answer.");
    };
    recorder.start();
    backend.recordingTimer = setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, 25000);
    toast("Recording… tap the mic to stop. Maximum 25 seconds.");
    document
      .querySelector("#mic")
      ?.setAttribute("aria-label", "Stop recording");
  });
}

bind = function () {
  original.bind();
  const on = (id, fn) => {
    const element = document.getElementById(id);
    if (element) element.onclick = fn;
  };
  on("mic", recordAudio);
  on("next", next);
  on("new", () => {
    if (
      window.confirm(
        "Start another visit for the current patient? Choose Cancel to enter a different patient.",
      )
    ) {
      const pid = backend.patientId;
      const old = { name: state.name, age: state.age, sex: state.sex };
      reset();
      backend.patientId = pid;
      Object.assign(state, old);
      render();
    } else reset();
  });
  on("end", () => {
    if (
      window.confirm(
        "Clear this device session? Saved patient records remain in the database.",
      )
    )
      reset();
  });
  on("downloadpdf", () => work(downloadDraft));
  for (const [id, decision] of [
    ["accept", "accept"],
    ["reject", "reject"],
  ])
    on(id, () =>
      work(async () => {
        capture();
        if (!backend.analysisId)
          throw new Error("Generate the clinical draft first.");
        const result = await CareAPI.json(
          `/api/consultation/${backend.consultationId}/review`,
          {
            method: "POST",
            body: {
              expected_version: backend.version,
              summary: changesOnly(),
              decision,
              doctor_notes: state.summary["Doctor notes"] ?? state.doctorNotes ?? "",
            },
          },
        );
        backend.version = result.version;
        state.review = result.status;
        render();
        toast("Review recorded. The PDF remains an assistance draft.");
      }),
    );
  const upload = document.querySelector("#upload");
  if (upload)
    upload.onchange = (event) => {
      const files = Array.from(event.target.files);
      void work(async () => {
        await saveIntake();
        for (const file of files) {
          const form = new FormData();
          form.set("consultation_id", backend.consultationId);
          form.set("expected_version", String(backend.version));
          form.set("file", file);
          const result = await CareAPI.json("/api/document/upload", {
            method: "POST",
            body: form,
          });
          backend.version = result.version;
          state.files.push({
            id: result.id,
            name: result.name,
            size: file.size,
            text: result.extracted_text,
          });
          backend.analysisId = null;
          backend.pdfUrl = null;
        }
        toast("Documents extracted and saved for analysis.");
      }).finally(() => render());
    };
  document.querySelectorAll("[data-remove]").forEach(
    (button) =>
      (button.onclick = () =>
        work(async () => {
          const id = button.dataset.remove;
          const result = await CareAPI.json(
            `/api/document/${encodeURIComponent(id)}?expected_version=${backend.version}`,
            { method: "DELETE" },
          );
          backend.version = result.version;
          state.files = state.files.filter((f) => f.id !== id);
          backend.analysisId = null;
          backend.pdfUrl = null;
          render();
        })),
  );
  const consent = document.querySelector("#consent");
  if (consent)
    consent.onchange = () => {
      if (!consent.checked && backend.consultationId)
        void work(async () => {
          const result = await CareAPI.json(
            `/api/consultation/${backend.consultationId}/consent`,
            {
              method: "PATCH",
              body: { expected_version: backend.version, consent: false },
            },
          );
          backend.version = result.version;
          backend.consent = false;
          state.consent = false;
          toast(
            "External processing consent revoked. Stored records are retained.",
          );
        });
    };
  const audio = document.querySelector("#audio");
  if (audio) {
    const previous = audio.onclick;
    audio.onclick = () => {
      capture();
      previous();
    };
  }
};

window.addEventListener("pagehide", () => {
  backend.epoch++;
  clearTimeout(backend.recordingTimer);
  backend.stream?.getTracks().forEach((track) => track.stop());
  if ("speechSynthesis" in window) speechSynthesis.cancel();
});

render();
void CareAPI.json("/api/system")
  .then((config) => {
    backend.config = config;
    capture();
    if (config.role === "doctor" && state.view === "intake" && state.step === 0 && !state.name && !state.age && !state.consent)
      state.view = "dashboard";
    render();
    const badge = document.querySelector(".demo");
    if (badge) badge.textContent = "AI DRAFT WORKSPACE";
  })
  .catch((error) => {
    const badge = document.querySelector(".demo");
    if (badge) badge.textContent = "BACKEND OFFLINE";
    toast(error.message);
  });
