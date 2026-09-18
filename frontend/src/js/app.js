/** Intake actions, input capture, event bindings, and application startup. */
function capture() {
  if (state.step === 0 && state.view === "intake") {
    state.name = document.querySelector("#name").value.trim();
    state.age = document.querySelector("#age").value;
    state.sex = document.querySelector("#sex").value;
    let mode = document.querySelector("#mode").value;
    if (mode !== state.mode) {
      state.answers = [];
      state.q = 0;
      state.choice = "";
      state.custom = "";
      state.summary = {};
    }
    state.mode = mode;
    state.consent = document.querySelector("#consent").checked;
  }
  if (document.querySelector("#share"))
    state.share = document.querySelector("#share").checked;
  document
    .querySelectorAll("[data-summary]")
    .forEach((e) => (state.summary[e.dataset.summary] = e.value));
  const doctorNotes = document.querySelector("#doctor-notes");
  if (doctorNotes) state.doctorNotes = doctorNotes.value;
  if (document.querySelector("#custom"))
    state.custom = document.querySelector("#custom").value;
}
function next() {
  toast(
    "The API connection has not loaded. Start the project server and reload.",
  );
}
function bind() {
  document.querySelectorAll("[data-view]").forEach(
    (e) =>
      (e.onclick = () => {
        capture();
        state.view = e.dataset.view;
        render();
      }),
  );
  document.querySelectorAll("[data-step]").forEach(
    (e) =>
      (e.onclick = () => {
        let n = +e.dataset.step;
        if (n > state.step)
          return toast("Continue through the current step first.");
        capture();
        state.step = n;
        render();
      }),
  );
  document.querySelectorAll("[data-answer]").forEach(
    (e) =>
      (e.onclick = () => {
        state.choice = e.dataset.answer;
        state.custom = "";
        render();
      }),
  );
  document.querySelectorAll("[data-remove]").forEach(
    (e) =>
      (e.onclick = () => {
        state.files = state.files.filter((f) => f.name !== e.dataset.remove);
        render();
      }),
  );
  const on = (id, fn) => {
    let e = document.getElementById(id);
    if (e) e.onclick = fn;
  };
  on("next", next);
  on("back", () => {
    capture();
    if (state.step === 1 && state.q > 0) {
      state.q--;
      state.choice = state.answers[state.q] || "";
      state.custom = "";
    } else state.step = Math.max(0, state.step - 1);
    render();
  });
  on("editprofile", () => {
    capture();
    state.step = 0;
    render();
  });
  on("privacy", () => {
    capture();
    state.step = 0;
    render();
  });
  on("new", () => {
    if (confirm("Start a new intake? This clears the current session."))
      reset();
  });
  on("end", () => {
    if (
      confirm(
        "Clear all patient details, answers, and local document references?",
      )
    )
      reset();
  });
  on("audio", () => {
    state.audio = !state.audio;
    if (state.audio)
      say(
        state.step === 1
          ? q().title
          : "Review your profile and consent before continuing.",
      );
    else if ("speechSynthesis" in window) speechSynthesis.cancel();
    render();
  });
  on("size", () => document.body.classList.toggle("large"));
  on("contrast", () => document.body.classList.toggle("contrast"));
  on("help", () =>
    toast(
      "Confirm your profile, answer the questions, add records, review your draft, then open the doctor console.",
    ),
  );
  on("adddocs", () => {
    state.view = "intake";
    state.step = 2;
    render();
  });
  on("readsummary", () => {
    capture();
    say(
      Object.entries(state.summary)
        .map(([k, v]) => k + ". " + v)
        .join(". "),
    );
  });
  for (const id of ["accept", "reject", "mic"]) {
    on(id, () =>
      toast("The API connection has not loaded. Reload the application."),
    );
  }
  document.querySelector("#language").onchange = (e) => {
    state.lang = e.target.value;
  };
  const upload = document.querySelector("#upload");
  if (upload)
    upload.onchange = () =>
      toast("The API connection has not loaded. Reload the application.");
}
function reset() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  state = {
    view: "intake",
    step: 0,
    q: 0,
    answers: [],
    choice: "",
    name: "",
    age: "",
    sex: "Prefer not to say",
    consent: false,
    share: false,
    mode: "General",
    submitted: false,
    files: [],
    audio: false,
    lang: "en-IN",
    custom: "",
    summary: {},
  };
  render();
  toast("Session cleared. Ready for a new patient.");
}
// integration.js renders once the authenticated workspace is fully connected.
