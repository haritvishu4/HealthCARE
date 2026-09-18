/** Accessible notices and browser speech narration. */
function toast(s) {
  document.querySelector(".toast")?.remove();
  let e = document.createElement("div");
  e.className = "toast";
  e.setAttribute("role", "status");
  e.textContent = s;
  document.body.append(e);
  setTimeout(() => e.remove(), 4500);
}
function say(s) {
  if (!("speechSynthesis" in window)) {
    toast("Audio narration is unavailable in this browser.");
    return;
  }
  speechSynthesis.cancel();
  let u = new SpeechSynthesisUtterance(s);
  u.lang = state.lang;
  speechSynthesis.speak(u);
}
