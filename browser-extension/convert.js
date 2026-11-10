import * as A from "./lib/api.js";
import { el, renderJobs, renderOptions, renderStatus, send, watchJobs } from "./lib/ui.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
let files = [];
let config = null;
const mine = new Set(); // jobs started from this tab

// ---------------------------------------------------------------- allowing downloads from websites

const waiting = params.get("allow");
if (waiting) {
  $("allow").classList.remove("hidden");
  $("pick").classList.add("hidden");
  $("convert").closest(".card").classList.add("hidden");
  mine.add(waiting);
  $("progress").classList.remove("hidden");
  $("allow-button").addEventListener("click", async () => {
    // Only the origins the extension needs are asked for, and only now.
    const granted = await chrome.permissions.request({ origins: ["<all_urls>"] });
    const result = $("allow-result");
    result.classList.remove("hidden");
    if (granted) {
      result.textContent = "Thank you. Converting now…";
      $("allow-button").disabled = true;
      await send({ type: "retry", id: waiting });
    } else {
      result.textContent = "Without this, ScanToDoc can only convert files you choose from your computer.";
    }
  });
}

// ---------------------------------------------------------------- choosing files

function addFiles(list) {
  const accepted = [...list].filter((f) => A.ACCEPTED.test(f.name));
  const skipped = list.length - accepted.length;
  files = [...files, ...accepted].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  showError(skipped ? `${skipped} file(s) skipped: ScanToDoc reads PDFs and pictures.` : "");
  renderFiles();
}

function renderFiles() {
  $("files").replaceChildren(
    ...files.map((f, i) =>
      el(
        "li",
        {},
        el("span", { title: f.name }, f.name),
        el("small", { class: "note" }, `${(f.size / 1e6).toFixed(1)} MB`),
        el("button", { class: "icon-btn", title: "Remove", onclick: () => (files.splice(i, 1), renderFiles()) }, "✕"),
      ),
    ),
  );
  $("convert").disabled = !files.length || !config;
  $("convert").textContent = files.length > 1 ? `Convert ${files.length} files into one document` : "Convert";
}

$("choose").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (e) => {
  addFiles(e.target.files);
  e.target.value = "";
});
const drop = $("drop");
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  addFiles(e.dataTransfer.files);
});

function showError(text) {
  $("error").textContent = text;
  $("error").classList.toggle("hidden", !text);
}

// ---------------------------------------------------------------- converting

$("convert").addEventListener("click", async () => {
  const button = $("convert");
  button.disabled = true;
  button.textContent = "Handing it to ScanToDoc…";
  showError("");
  try {
    const name = $("name").value.trim();
    const project = await A.createProject(files.map((f) => ({ blob: f, filename: f.name })), name);
    const settings = await A.getSettings();
    const reply = await send({
      type: "track",
      pid: project.id,
      name: project.name,
      options: {
        format: settings.format,
        preset: settings.preset,
        languages: settings.languages,
        pages: ($("pages") && $("pages").value.trim()) || null,
      },
    });
    if (!reply || !reply.ok) throw new Error((reply && reply.error) || "The extension did not answer.");
    mine.add(reply.result.id);
    $("progress").classList.remove("hidden");
    files = [];
    $("name").value = "";
  } catch (err) {
    showError(err.message || String(err));
  }
  renderFiles();
});

async function refresh() {
  config = await renderStatus($("status"), refresh);
  await renderOptions($("options"), config, { pages: true });
  renderFiles();
}

watchJobs((jobs) => renderJobs($("jobs"), jobs.filter((j) => mine.has(j.id))));
refresh();
