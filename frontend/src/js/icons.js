/** Inline interface icons and HTML escaping. */
const paths = {
  plus: "M12 4v16M4 12h16",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  heart:
    "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z",
  file: "M14 2H5v20h14V7zM14 2v6h5M8 12h8M8 16h8",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6zM8 12l3 3 5-6",
  mic: "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8",
  arrow: "M5 12h14M14 7l5 5-5 5",
  sound: "M11 4 5 9H2v6h3l6 5zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3z",
  check: "m5 12 4 4L19 6",
  upload: "M12 16V3M7 8l5-5 5 5M4 16v5h16v-5",
  doctor:
    "M8 3v7a4 4 0 0 0 8 0V3M8 4H5M16 4h3M12 14v3a4 4 0 0 0 8 0v-3M22 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
};
const icon = (n) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[n] || paths.file}"/></svg>`;
const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
