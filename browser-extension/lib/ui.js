// Pieces shared by the popup and the convert page.

import * as A from "./api.js";

const README = "https://github.com/jellotoo/scantodoc";

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children.flat()) {
    if (child != null && child !== false) node.append(child);
  }
  return node;
}

export const send = (message) => chrome.runtime.sendMessage(message);

// ---------------------------------------------------------------- is ScanToDoc running?

/** Show whether ScanToDoc answers; returns its /api/config, or null. */
export async function renderStatus(box, onRetry) {
  box.className = "status";
  box.replaceChildren(el("span", { class: "dot" }), el("p", {}, "Looking for ScanToDoc on this computer…"));
  let config;
  try {
    config = await A.getConfig();
  } catch (err) {
    box.className = "status bad";
    box.replaceChildren(
      el("span", { class: "dot" }),
      el(
        "div",
        {},
        el("p", {}, "ScanToDoc isn't running on this computer."),
        el(
          "p",
          { class: "sub" },
          "Start it by double-clicking ",
          el("b", {}, "start-windows.bat"),
          " (Windows) or ",
          el("b", {}, "start-mac.command"),
          " (Mac) in the ScanToDoc folder. ",
          el("a", { href: `${README}#1-install-and-start`, target: "_blank" }, "How to install it"),
        ),
        el("p", {}, el("button", { class: "btn small", onclick: onRetry, "data-testid": "retry" }, "Try again")),
      ),
    );
    return null;
  }
  const names = Object.fromEntries(A.LANGUAGES);
  const langs = A.LANGUAGES.map(([code]) => code).filter((c) => config.languages.includes(c));
  if (!config.tesseract) {
    box.className = "status warn";
    box.replaceChildren(
      el("span", { class: "dot" }),
      el(
        "div",
        {},
        el("p", {}, "ScanToDoc is running, but its free page reader (Tesseract) isn't installed."),
        el("p", { class: "sub" }, el("a", { href: `${README}#install-tesseract`, target: "_blank" }, "How to install Tesseract")),
      ),
    );
  } else {
    box.className = "status ok";
    box.replaceChildren(
      el("span", { class: "dot" }),
      el(
        "div",
        { "data-testid": "connected" },
        el("p", {}, "ScanToDoc is running"),
        el("p", { class: "sub" }, `Free reader: ${langs.map((c) => names[c]).join(", ") || "installed"}`),
      ),
    );
  }
  return config;
}

// ---------------------------------------------------------------- options

/** Format, look and languages; every change is remembered for next time. */
export async function renderOptions(box, config, { pages = false } = {}) {
  const settings = await A.getSettings();
  let presets = [];
  try {
    presets = await A.getPresets();
  } catch {
    presets = [{ key: "keep-original", name: "Keep original" }];
  }
  const formats = A.FORMATS.filter(([id]) => id !== "pdf" || !config || config.chromium);
  const save = (changes) => A.saveSettings(changes);

  const format = el(
    "select",
    { id: "format", "data-testid": "format", onchange: (e) => save({ format: e.target.value }) },
    formats.map(([id, label]) => el("option", { value: id, selected: id === settings.format }, label)),
  );
  const preset = el(
    "select",
    { id: "preset", "data-testid": "preset", onchange: (e) => save({ preset: e.target.value }) },
    presets.map((p) => el("option", { value: p.key, selected: p.key === settings.preset }, p.name)),
  );
  const installed = config ? config.languages : A.LANGUAGES.map(([c]) => c);
  const shown = A.LANGUAGES.filter(([code]) => installed.includes(code));
  const langs = el(
    "div",
    { class: "langs" },
    shown.map(([code, label]) =>
      el(
        "label",
        {},
        el("input", {
          type: "checkbox",
          value: code,
          checked: settings.languages.includes(code),
          onchange: () => save({ languages: [...langs.querySelectorAll("input:checked")].map((i) => i.value) }),
        }),
        label,
      ),
    ),
  );
  const rows = [
    el("label", { class: "name", for: "format" }, "Save as"),
    format,
    el("label", { class: "name", for: "preset" }, "Look"),
    preset,
  ];
  if (shown.length) rows.push(el("span", { class: "name" }, "Languages"), langs);
  if (pages) {
    rows.push(
      el("label", { class: "name", for: "pages" }, "Pages"),
      el("input", { type: "text", id: "pages", placeholder: "All (or e.g. 1-10, 15)", "data-testid": "pages" }),
    );
  }
  box.replaceChildren(...rows);
}

// ---------------------------------------------------------------- jobs

function describe(job) {
  switch (job.step) {
    case "fetching":
      return "Downloading from the website…";
    case "uploading":
      return "Handing it to ScanToDoc…";
    case "starting":
      return "Starting…";
    case "converting":
      if (!job.total) return "Preparing the pages…";
      if (job.done >= job.total) return "Finishing…";
      return `Reading page ${job.done + 1} of ${job.total}…`;
    case "downloading":
      return "Saving the file…";
    case "needs-permission":
      return "Waiting for your permission to download files from websites.";
    case "done":
      return `Saved ${job.file || "the file"} to your Downloads folder.`;
    default:
      return job.error || "Something went wrong.";
  }
}

function bar(job) {
  if (job.step === "done") return el("div", { class: "bar" }, el("div", { style: "width:100%" }));
  if (job.step === "error" || job.step === "needs-permission") return null;
  if (job.step === "converting" && job.total) {
    return el("div", { class: "bar" }, el("div", { style: `width:${Math.round((100 * job.done) / job.total)}%` }));
  }
  return el("div", { class: "bar indeterminate" }, el("div"));
}

export function renderJobs(box, jobs, { emptyText = "" } = {}) {
  if (!jobs.length) {
    box.replaceChildren(emptyText ? el("p", { class: "empty" }, emptyText) : "");
    return;
  }
  box.replaceChildren(
    ...jobs.map((job) => {
      const act = (type) => () => send({ type, id: job.id });
      const open = async () => chrome.tabs.create({ url: await A.appUrl(job.pid) });
      const allow = () => chrome.tabs.create({ url: chrome.runtime.getURL(`convert.html?allow=${job.id}`) });
      const busy = !["done", "error", "needs-permission"].includes(job.step);
      return el(
        "div",
        { class: `job ${job.step}`, "data-testid": "job", "data-step": job.step },
        el(
          "div",
          { class: "top" },
          el("span", { class: "name", title: job.name }, job.name),
          busy ? null : el("button", { class: "icon-btn", title: "Remove from this list", onclick: act("remove") }, "✕"),
        ),
        el("p", { class: "text", "data-testid": "job-text" }, describe(job)),
        job.step === "done" && job.warning ? el("p", { class: "warning" }, job.warning) : null,
        bar(job),
        el(
          "div",
          { class: "actions" },
          job.step === "done" ? el("button", { class: "btn small", onclick: act("show") }, "Show file") : null,
          job.pid && (job.step === "done" || job.step === "error")
            ? el("button", { class: "btn small", onclick: open }, "Open in ScanToDoc")
            : null,
          job.step === "converting" ? el("button", { class: "btn small", onclick: act("stop") }, "Stop") : null,
          job.step === "error" && job.error !== "Stopped." ? el("button", { class: "btn small", onclick: act("retry") }, "Try again") : null,
          job.step === "needs-permission" ? el("button", { class: "btn small primary", onclick: allow }, "Allow…") : null,
        ),
      );
    }),
  );
}

export function watchJobs(callback) {
  const read = async () => callback((await chrome.storage.local.get("jobs")).jobs || []);
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.jobs) callback(changes.jobs.newValue || []);
  });
  read();
}
