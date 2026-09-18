/** API transport. Provider keys belong only in backend/.env. */
const CareAPI = {
  base: window.CARE_API_BASE || "",
  async request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    // In production, your existing auth host supplies a Supabase access token in memory.
    // The local development proxy injects its own server-side token.
    if (window.CARE_ACCESS_TOKEN)
      headers.set("Authorization", `Bearer ${window.CARE_ACCESS_TOKEN}`);
    if (options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
      options.body = JSON.stringify(options.body);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 70000);
    try {
      const response = await fetch(this.base + path, {
        ...options,
        headers,
        signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 401 && window.CareAuth?.user) {
          window.CareAuth.expireSession();
          throw new Error("Your session has expired. Please sign in again.");
        }
        const error = await response.json().catch(() => ({}));
        throw new Error(
          typeof error.detail === "string"
            ? error.detail
            : `Request failed (${response.status}).`,
        );
      }
      return response;
    } catch (error) {
      if (error.name === "AbortError")
        throw new Error(
          "The request timed out. Reload the saved consultation before retrying.",
        );
      if (error instanceof TypeError)
        throw new Error(
          "Backend unavailable. Start the project and open its localhost address.",
        );
      throw error;
    } finally {
      clearTimeout(timer);
    }
  },
  async json(path, options) {
    return (await this.request(path, options)).json();
  },
  async download(path, filename) {
    const blob = await (await this.request(path)).blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  },
};
