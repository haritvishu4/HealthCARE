/** Local workspace authentication. Session credentials stay in an HttpOnly cookie. */
(() => {
  "use strict";

  const root = document.getElementById("app");
  const shield = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 7v5c0 5 8 9 8 9s8-4 8-9V7Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg>';
  const arrow = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h16m-6-6 6 6-6 6"/></svg>';
  const eye = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  let configured = true;
  let appLoading = false;
  let sessionCheckPending = false;
  let leavingWorkspace = false;

  async function request(path, data) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, {
        method: data === undefined ? "GET" : "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: data === undefined ? {} : { "Content-Type": "application/json" },
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: controller.signal,
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(typeof result.detail === "string"
          ? result.detail : `Unable to complete this request (${response.status}).`);
        error.status = response.status;
        throw error;
      }
      if (typeof result.authenticated !== "boolean" || typeof result.configured !== "boolean") {
        throw new Error("The workspace could not verify your session. Restart the project server and try again.");
      }
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The connection timed out. Please try again.");
      if (error instanceof TypeError) throw new Error("Cannot connect to Care. Check that the project server is running, then try again.");
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  function frame(content) {
    document.body.classList.add("auth-mode");
    root.innerHTML = `
      <main class="auth-screen">
        <section class="auth-story" aria-label="Care workspace">
          <a class="auth-brand" href="/" aria-label="Care home"><span class="auth-brandmark" aria-hidden="true">+</span><span>care<span class="auth-branddot">.</span></span></a>
          <div class="auth-story-content">
            <div class="auth-eyebrow"><span></span> YOUR CARE WORKSPACE</div>
            <h1>A little less paperwork.<br><span>A little more care.</span></h1>
            <p>Bring the patient's story together, from the first question to a clearer consultation.</p>
            <div class="auth-preview" aria-hidden="true">
              <div class="auth-preview-head"><span class="auth-preview-icon">${shield}</span><div><strong>Ready for better conversations</strong><small>Everything you need, in one place</small></div><span class="auth-preview-dot"></span></div>
              <div class="auth-preview-row"><span>01</span><div><strong>Patient intake</strong><small>A thoughtful start to every visit</small></div><span class="auth-preview-check">✓</span></div>
              <div class="auth-preview-row"><span>02</span><div><strong>Medical records</strong><small>The context behind the symptoms</small></div><span class="auth-preview-check">✓</span></div>
              <div class="auth-preview-row"><span>03</span><div><strong>Consultation summaries</strong><small>Clear drafts for your review</small></div><span class="auth-preview-check">✓</span></div>
            </div>
          </div>
          <div class="auth-story-footer">${shield}<span>Thoughtful tools. Human care.</span></div>
        </section>
        <section class="auth-panel" aria-label="Workspace access">
          <div class="auth-panel-top"><span class="auth-workspace-dot"></span> Care Intake <span class="auth-local">LOCAL WORKSPACE</span></div>
          <div class="auth-form-wrap">${content}</div>
          <p class="auth-panel-footer">Your patients' stories deserve your full attention.</p>
        </section>
      </main>`;
  }

  function status(message, isError = true) {
    const element = document.getElementById("auth-status");
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("is-error", isError);
    element.hidden = !message;
  }

  function showLogin(isConfigured = configured, forceSetup = false) {
    configured = isConfigured;
    const setup = !configured || forceSetup;
    window.CareAuth.user = null;
    document.title = setup ? "Care | Set up your workspace" : "Care | Sign in";
    frame(`
      <div class="auth-form-icon">${shield}</div>
      <div class="auth-form-eyebrow">${setup ? "LET'S GET STARTED" : "WELCOME BACK"}</div>
      <h2>${setup ? "Set up your workspace" : "Good care starts here."}</h2>
      <p class="auth-form-description">${setup ? "Create your workspace login to access patient intake, records, and consultation summaries." : "Sign in to continue to your Care workspace."}</p>
      <form id="auth-form">
        ${setup ? '<div class="auth-field"><label for="auth-name">Your name</label><input id="auth-name" name="name" type="text" autocomplete="name" placeholder="Enter your name" maxlength="100" required /></div>' : ""}
        <div class="auth-field auth-role-field">
          <label>Workspace role</label>
          <div class="auth-role-selector" role="radiogroup" aria-label="Workspace role">
            <button type="button" class="auth-role-option is-selected" data-role="patient" role="radio" aria-checked="true">
              <span class="auth-role-icon">P</span>
              <span>Patient</span>
            </button>
            <button type="button" class="auth-role-option" data-role="doctor" role="radio" aria-checked="false">
              <span class="auth-role-icon">D</span>
              <span>Doctor</span>
            </button>
          </div>
          <input id="auth-role" name="role" type="hidden" value="patient" />
        </div>
        <div class="auth-field"><label for="auth-email">Email address</label><input id="auth-email" name="email" type="email" autocomplete="username" inputmode="email" autocapitalize="none" spellcheck="false" placeholder="you@clinic.com" maxlength="254" required /></div>
        <div class="auth-field"><label for="auth-password">Password</label><div class="auth-password-wrap"><input id="auth-password" name="password" type="password" autocomplete="${setup ? "new-password" : "current-password"}" placeholder="${setup ? "Create a password" : "Enter your password"}" minlength="${setup ? 12 : 1}" maxlength="128" ${setup ? 'aria-describedby="auth-password-help"' : ""} required /><button class="auth-password-toggle" type="button" aria-label="Show password" aria-controls="auth-password" aria-pressed="false">${eye}</button></div>${setup ? '<p class="auth-field-help" id="auth-password-help">Use 12–128 characters.</p>' : ""}</div>
        ${setup ? '<div class="auth-field"><label for="auth-confirm">Confirm password</label><input id="auth-confirm" name="confirm-password" type="password" autocomplete="new-password" placeholder="Re-enter your password" minlength="12" maxlength="128" required /></div>' : ""}
        <p class="auth-status" id="auth-status" role="alert" aria-live="polite" hidden></p>
        <button class="auth-submit" id="auth-submit" type="submit"><span>${setup ? "Create workspace login" : "Sign in"}</span>${arrow}</button>
      </form>
        <p class="auth-switch">${setup ? "Already have an account?" : "Don't have an account?"} <button id="auth-switch" type="button">${setup ? "Sign in" : "Create one"}</button></p>
      <div class="auth-access-note">${shield}<p>${setup ? "This login protects your existing workspace. Saved patient records stay available after setup." : "For your clinic's authorized workspace user. Sign out when you finish on a shared computer."}</p></div>
    `);

    const form = document.getElementById("auth-form");
    const password = document.getElementById("auth-password");
    const confirmation = document.getElementById("auth-confirm");
    const toggle = form.querySelector(".auth-password-toggle");
    const roleInput = document.getElementById("auth-role");
    const roleButtons = form.querySelectorAll(".auth-role-option");
    roleButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const nextRole = button.dataset.role;
        roleInput.value = nextRole;
        roleButtons.forEach((item) => {
          const selected = item === button;
          item.classList.toggle("is-selected", selected);
          item.setAttribute("aria-checked", String(selected));
        });
      });
    });
    document.getElementById("auth-switch").addEventListener("click", () => {
      showLogin(setup ? true : configured, !setup);
    });
    toggle.addEventListener("click", () => {
      const visible = password.type === "password";
      password.type = visible ? "text" : "password";
      toggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
      toggle.setAttribute("aria-pressed", String(visible));
    });
    if (confirmation) {
      const validateConfirmation = () => confirmation.setCustomValidity(
        confirmation.value && password.value !== confirmation.value ? "Your passwords do not match." : "",
      );
      confirmation.addEventListener("input", validateConfirmation);
      password.addEventListener("input", validateConfirmation);
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.getAttribute("aria-busy") === "true" || !form.reportValidity()) return;
      const button = document.getElementById("auth-submit");
      const buttonLabel = button.querySelector("span");
      const originalLabel = buttonLabel.textContent;
      const data = {
        email: document.getElementById("auth-email").value.trim(),
        password: password.value,
        role: document.getElementById("auth-role")?.value || "patient",
      };
      if (setup) {
        data.name = document.getElementById("auth-name").value.trim();
        if (!data.name) {
          status("Please enter your name.");
          document.getElementById("auth-name").focus();
          return;
        }
      }
      status("");
      form.setAttribute("aria-busy", "true");
      button.disabled = true;
      buttonLabel.textContent = setup ? "Creating your login…" : "Signing in…";
      try {
        const session = await request(setup ? "/auth/setup" : "/auth/login", data);
        if (!session.authenticated || !session.user) throw new Error("Sign in could not be completed. Please try again.");
        form.reset();
        if (window.CareAuth) window.CareAuth.role = data.role || "patient";
        await openWorkspace(session);
      } catch (error) {
        if (setup && error.status === 409) {
          showLogin(true);
          status("This workspace already has a login. Sign in with its email and password.");
          return;
        }
        status(error.message);
      } finally {
        delete data.password;
        form.setAttribute("aria-busy", "false");
        button.disabled = false;
        buttonLabel.textContent = originalLabel;
      }
    });
  }

  async function openWorkspace(session) {
    if (appLoading) return;
    appLoading = true;
    configured = session.configured;
    window.CareAuth.user = session.user;
    document.title = "Care | Patient intake";
    document.body.classList.remove("auth-mode");
    root.innerHTML = '<div class="auth-loading" role="status"><span class="auth-brandmark" aria-hidden="true">+</span><p>Opening your Care workspace…</p></div>';
    try {
      for (const name of ["icons", "state", "helpers", "views", "app", "api", "dashboard", "integration"]) {
        await new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = `./src/js/${name}.js`;
          script.onload = resolve;
          script.onerror = () => reject(new Error("Care could not load. Please reload the page to try again."));
          document.body.append(script);
        });
      }
    } catch (error) {
      frame('<div class="auth-form-icon">' + shield + '</div><h2>Let’s try that again.</h2><p class="auth-form-description" id="auth-load-error"></p><button class="auth-submit" id="auth-reload" type="button">Reload workspace</button>');
      document.getElementById("auth-load-error").textContent = error.message;
      document.getElementById("auth-reload").onclick = () => window.location.reload();
    }
  }

  async function checkSession() {
    try {
      const session = await request("/auth/session");
      configured = session.configured;
      if (session.authenticated && session.user) await openWorkspace(session);
      else showLogin(session.configured);
    } catch (error) {
      frame('<div class="auth-form-icon">' + shield + '</div><div class="auth-form-eyebrow">WORKSPACE CONNECTION</div><h2>We couldn’t open Care.</h2><p class="auth-form-description" id="auth-connection-error" role="alert"></p><button class="auth-submit" id="auth-retry" type="button">Try again</button>');
      document.getElementById("auth-connection-error").textContent = error.message;
      document.getElementById("auth-retry").onclick = async (event) => {
        event.currentTarget.disabled = true;
        event.currentTarget.textContent = "Connecting…";
        await checkSession();
      };
    }
  }

  window.CareAuth = {
    user: null,
    expireSession() {
      if (leavingWorkspace) return;
      leavingWorkspace = true;
      window.location.reload();
    },
    async logout() {
      const session = await request("/auth/logout", {});
      if (session.authenticated) throw new Error("Sign out could not be completed. Please try again.");
      window.location.reload();
    },
  };

  // Recheck after returning to this tab, including a sign-out in another tab.
  // A full reload clears all patient state and loads the application scripts once.
  async function refreshSession() {
    if (!window.CareAuth.user || sessionCheckPending || leavingWorkspace || document.hidden) return;
    sessionCheckPending = true;
    try {
      const session = await request("/auth/session");
      if (!session.authenticated) window.CareAuth.expireSession();
    } catch {
      // Transient connection errors are reported by the next user action.
    } finally {
      sessionCheckPending = false;
    }
  }
  window.addEventListener("focus", refreshSession);
  document.addEventListener("visibilitychange", refreshSession);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
  });
  setInterval(refreshSession, 60000);
  checkSession();
})();
