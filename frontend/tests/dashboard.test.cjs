const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function views() {
  const context = vm.createContext({});
  for (const file of ["icons.js", "state.js", "views.js", "dashboard.js"]) {
    const filename = path.join(__dirname, "../src/js", file);
    vm.runInContext(readFileSync(filename, "utf8"), context, { filename });
  }
  return {
    dashboard(data, status = "all") {
      context.page = data;
      context.filter = status;
      return vm.runInContext(
        "doctorDashboard.status = filter; dashboardContents(page)", context,
      );
    },
    summary(data) {
      context.savedSummary = data;
      return vm.runInContext("state.summary = savedSummary; summary()", context);
    },
  };
}

const stats = { total: 57, pending: 18, reviewed: 21, rejected: 6, draft: 12 };
const visit = {
  id: "synthetic-visit", name: "Test Patient", age: 32, gender: "Female",
  mode: "General", status: "draft", has_analysis: true, updated_at: 1_700_000_000,
};

function page(items, overrides = {}) {
  return {
    stats, items, offset: 0, limit: 10, total_matches: items.length, has_more: false,
    ...overrides,
  };
}

function buttons(html) {
  return Array.from(html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g),
    ([, attributes, content]) => ({ attributes, content }));
}

test("patient names and saved summary keys remain text, including inside attributes", () => {
  const render = views();
  const name = '<img src=x onerror="alert(1)"> & Ada';
  const escapedName = "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; Ada";
  const dashboard = render.dashboard(page([{ ...visit, name }]));
  assert.ok(dashboard.includes(`<strong>${escapedName}</strong>`));
  assert.ok(dashboard.includes(`aria-label="Open consultation for ${escapedName}"`));
  assert.doesNotMatch(dashboard, /<img\b/);

  const label = '<img src=x onerror="alert(1)"> & "History"';
  const escapedLabel = "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &quot;History&quot;";
  const summary = render.summary({ [label]: "</textarea><script>alert(1)</script>" });
  assert.ok(summary.includes(`<label>${escapedLabel}<textarea`));
  assert.ok(summary.includes(`data-summary="${escapedLabel}"`));
  assert.ok(summary.includes("&lt;/textarea&gt;&lt;script&gt;alert(1)&lt;/script&gt;"));
  assert.doesNotMatch(summary, /<(?:img|script)\b/);
});

test("queue rows distinguish prepared drafts, completed decisions, and unfinished intake", () => {
  const items = [
    { ...visit, id: "pending" },
    { ...visit, id: "reviewed", status: "reviewed" },
    { ...visit, id: "rejected", status: "rejected" },
    { ...visit, id: "intake", status: "intake", has_analysis: false },
  ];
  const html = views().dashboard(page(items));
  const rows = html.match(/<tr><td>[\s\S]*?<\/tr>/g);
  assert.equal(rows.length, 4);
  for (const [index, label, action] of [
    [0, "Awaiting review", "Review"],
    [1, "Reviewed", "Review"],
    [2, "Rejected", "Review"],
    [3, "Intake in progress", "View intake"],
  ]) {
    assert.ok(rows[index].includes(`</span>${label}</span>`));
    const open = buttons(rows[index]).find((button) => button.attributes.includes("data-doctor-open"));
    assert.ok(open.content.startsWith(`${action} `));
  }
});

test("a filtered page shows whole-workspace metrics and the server's matching range", () => {
  const html = views().dashboard(page(
    [visit, { ...visit, id: "second-visit" }],
    { offset: 10, total_matches: 18, has_more: true },
  ), "pending");
  const controls = buttons(html);
  const metrics = Object.fromEntries(controls
    .filter((button) => /class="doctor-metric\b/.test(button.attributes))
    .map((button) => [
      button.attributes.match(/data-doctor-filter="([^"]+)"/)[1],
      Number(button.content.match(/<strong>(\d+)<\/strong>/)[1]),
    ]));
  assert.deepEqual(metrics, { all: 57, pending: 18, reviewed: 21, draft: 12 });
  assert.match(html, /11–12 of 18/);
  const selectedFilters = controls.filter((button) => /aria-pressed="true"/.test(button.attributes));
  assert.equal(selectedFilters.length, 2); // The metric card and its matching filter.
  assert.ok(selectedFilters.every((button) => /data-doctor-filter="pending"/.test(button.attributes)));
  for (const id of ["doctor-previous", "doctor-next"]) {
    const control = controls.find((button) => button.attributes.includes(`id="${id}"`));
    assert.doesNotMatch(control.attributes, /\bdisabled\b/);
  }
});

test("empty workspace and empty filter offer distinct recovery actions", () => {
  const render = views();
  const emptyWorkspace = render.dashboard(page([], {
    stats: { total: 0, pending: 0, reviewed: 0, rejected: 0, draft: 0 },
  }));
  assert.match(emptyWorkspace, /Your next consultation starts here\./);
  assert.match(emptyWorkspace, /id="doctor-start-intake"/);

  const emptyFilter = render.dashboard(page([], {
    stats: { total: 3, pending: 0, reviewed: 3, rejected: 0, draft: 0 },
  }), "pending");
  assert.match(emptyFilter, /No consultations in this view\./);
  assert.match(emptyFilter, /data-doctor-filter="all">View all consultations/);
  assert.doesNotMatch(emptyFilter, /id="doctor-start-intake"/);
  for (const html of [emptyWorkspace, emptyFilter]) {
    assert.match(html, /0 consultations/);
    const pagination = buttons(html).filter((button) => /id="doctor-(?:previous|next)"/.test(button.attributes));
    assert.equal(pagination.length, 2);
    assert.ok(pagination.every((button) => /\bdisabled\b/.test(button.attributes)));
  }
});
