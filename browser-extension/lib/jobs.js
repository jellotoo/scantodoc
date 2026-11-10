// Conversions run here, in the background, so they keep going after the popup
// closes. Each job is saved in chrome.storage.local, so the popup can show it
// and the job can carry on if Chrome restarts the background worker.
//
//   fetching -> uploading -> starting -> converting -> downloading -> done
//   (or "needs-permission" until the person allows downloads from websites,
//    or "error" at any point)

import * as A from "./api.js";

const KEEP = 20;
const ACTIVE = new Set(["fetching", "uploading", "starting", "converting", "downloading"]);
const running = new Set();

const MIME_EXT = {
  "application/pdf": ".pdf",
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/tiff": ".tif",
  "image/webp": ".webp",
  "image/gif": ".gif",
  "image/bmp": ".bmp",
};

// ---------------------------------------------------------------- storage

export async function listJobs() {
  const { jobs } = await chrome.storage.local.get("jobs");
  return jobs || [];
}

async function saveJobs(jobs) {
  await chrome.storage.local.set({ jobs: jobs.slice(0, KEEP) });
  await updateBadge(jobs);
}

export async function getJob(id) {
  return (await listJobs()).find((j) => j.id === id);
}

async function update(id, changes) {
  const jobs = await listJobs();
  const job = jobs.find((j) => j.id === id);
  if (!job) return null;
  Object.assign(job, changes);
  await saveJobs(jobs);
  return job;
}

async function addJob(fields) {
  const settings = await A.getSettings();
  const job = {
    id: crypto.randomUUID(),
    pid: null,
    name: "document",
    step: "fetching",
    done: 0,
    total: 0,
    error: "",
    format: settings.format,
    preset: settings.preset,
    languages: settings.languages,
    pages: null,
    downloadId: null,
    started: Date.now(),
    ...fields,
  };
  await saveJobs([job, ...(await listJobs())]);
  return job;
}

export async function removeJob(id) {
  await saveJobs((await listJobs()).filter((j) => j.id !== id));
}

export async function clearFinished() {
  await saveJobs((await listJobs()).filter((j) => ACTIVE.has(j.step) || j.step === "needs-permission"));
}

async function updateBadge(jobs) {
  const active = jobs.filter((j) => ACTIVE.has(j.step));
  let text = "";
  if (active.length === 1 && active[0].step === "converting" && active[0].total) {
    text = `${active[0].done}/${active[0].total}`;
  } else if (active.length) {
    text = String(active.length);
  }
  await chrome.action.setBadgeBackgroundColor({ color: "#4f46e5" });
  await chrome.action.setBadgeText({ text });
  if (active.length) await chrome.alarms.create("resume", { periodInMinutes: 0.5 });
  else await chrome.alarms.clear("resume");
}

// ---------------------------------------------------------------- starting jobs

/** Convert a PDF or picture found on a web page (a link, an image, or the tab itself). */
export async function startFromUrl(url) {
  const job = await addJob({ source: "web", url, name: nameFromUrl(url) });
  run(job.id);
  return job;
}

/** Carry on with a project the convert page has just uploaded. */
export async function startFromProject(pid, name, options = {}) {
  const job = await addJob({ source: "file", pid, name, step: "starting", ...options });
  run(job.id);
  return job;
}

/** Try a web job again, for example after the person allowed downloads from websites. */
export async function retry(id) {
  const job = await getJob(id);
  if (!job) return;
  await update(id, { step: job.pid ? "starting" : "fetching", error: "", done: 0 });
  run(id);
}

export async function stop(id) {
  const job = await getJob(id);
  if (!job) return;
  if (job.pid && job.step === "converting") {
    try {
      await A.cancel(job.pid);
    } catch {
      /* the app may be gone; the job is stopped here anyway */
    }
  }
  await update(id, { step: "error", error: "Stopped." });
}

/** After the background worker restarts: pick up jobs that were waiting on the app. */
export async function resumeAll() {
  for (const job of await listJobs()) {
    if (running.has(job.id)) continue;
    if (job.step === "converting" || job.step === "downloading") run(job.id);
    else if (ACTIVE.has(job.step) && Date.now() - job.started > 120000) {
      // Fetching or uploading never takes this long: the worker was stopped mid-way.
      await update(job.id, { step: "error", error: "Interrupted. Please try again." });
    }
  }
}

// ---------------------------------------------------------------- the steps

async function run(id) {
  if (running.has(id)) return;
  running.add(id);
  try {
    let job = await getJob(id);
    if (job.step === "fetching") {
      const file = await fetchFile(job.url);
      if (!file) {
        await update(id, { step: "needs-permission" });
        await chrome.tabs.create({ url: chrome.runtime.getURL(`convert.html?allow=${id}`) });
        return;
      }
      job = await update(id, { step: "uploading", name: file.filename.replace(/\.[^.]+$/, "") });
      const project = await A.createProject([file], job.name);
      job = await update(id, { step: "starting", pid: project.id });
    }
    if (job.step === "starting") {
      const config = await A.getConfig();
      if (!config.tesseract) {
        throw new Error("The free page reader (Tesseract) is not installed on this computer. See \"Install Tesseract\" in ScanToDoc's README.");
      }
      if (job.format === "pdf" && !config.chromium) {
        throw new Error("PDF needs Chrome, Edge or Chromium installed for ScanToDoc. Choose Word instead, then use Save as PDF.");
      }
      await A.setStyle(job.pid, job.preset).catch(() => A.setStyle(job.pid, A.DEFAULTS.preset));
      await A.startConvert(job.pid, { languages: A.usableLanguages(job.languages, config.languages), pages: job.pages });
      job = await update(id, { step: "converting" });
    }
    if (job.step === "converting") {
      job = await waitForConversion(id);
      if (!job) return;
    }
    if (job.step === "downloading") {
      await download(job);
    }
  } catch (err) {
    const message = err instanceof A.ServerDown ? err.message : `${err.message || err}`;
    await update(id, { step: "error", error: message });
    await notify(id, "Could not convert", message);
  } finally {
    running.delete(id);
  }
}

async function waitForConversion(id) {
  let misses = 0;
  for (;;) {
    let job = await getJob(id);
    if (!job || job.step !== "converting") return null; // stopped or removed
    let progress;
    try {
      progress = await A.getProgress(job.pid);
      misses = 0;
    } catch (err) {
      if (err instanceof A.ServerDown && ++misses < 5) {
        await sleep(2000);
        continue;
      }
      throw err;
    }
    job = await update(id, { done: progress.done + progress.failed, total: progress.total });
    if (progress.status === "done" || progress.status === "partial") {
      const note = progress.failed ? `${progress.failed} page(s) could not be read.` : "";
      return update(id, { step: "downloading", warning: note });
    }
    if (progress.status !== "converting" && progress.status !== "new") {
      throw new Error(progress.error || (progress.status === "cancelled" ? "Stopped." : "The conversion stopped. Open it in ScanToDoc to see why."));
    }
    await sleep(800);
  }
}

async function download(job) {
  const url = await A.exportUrl(job.pid, job.format);
  const downloadId = await chrome.downloads.download({ url, conflictAction: "uniquify" });
  await update(job.id, { downloadId });
  const item = await waitForDownload(downloadId);
  if (item.state !== "complete") {
    throw new Error(`The ${job.format.toUpperCase()} file could not be saved (${item.error || "download stopped"}). Open it in ScanToDoc to try again.`);
  }
  const file = item.filename.split(/[\\/]/).pop();
  await update(job.id, { step: "done", file, finished: Date.now() });
  await notify(job.id, "Your document is ready", `${file} was saved to your Downloads folder.`);
}

function waitForDownload(downloadId) {
  return new Promise((resolve) => {
    const check = async () => {
      const [item] = await chrome.downloads.search({ id: downloadId });
      if (!item || item.state !== "in_progress") {
        chrome.downloads.onChanged.removeListener(onChanged);
        resolve(item || { state: "interrupted", error: "removed" });
      }
    };
    const onChanged = (delta) => {
      if (delta.id === downloadId && delta.state) check();
    };
    chrome.downloads.onChanged.addListener(onChanged);
    check();
  });
}

// ---------------------------------------------------------------- fetching from the web

/** Download a file from the web page's site. Returns null when the person first has to
 *  allow the extension to read files from websites. */
async function fetchFile(url) {
  if (/^file:/i.test(url)) {
    throw new Error("Files on your computer can't be read from the page. Click the ScanToDoc button and choose \"Convert files from this computer\".");
  }
  if (/^blob:/i.test(url)) {
    throw new Error("This picture only exists inside the page. Save it to your computer first, then convert it from the ScanToDoc button.");
  }
  let response;
  try {
    response = await fetch(url, { credentials: "include" });
  } catch {
    if (/^https?:/i.test(url) && !(await chrome.permissions.contains({ origins: ["<all_urls>"] }))) return null;
    throw new Error("The website did not let ScanToDoc download that file.");
  }
  if (!response.ok) throw new Error(`The website answered ${response.status} when downloading the file.`);
  const type = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (type === "text/html") throw new Error("That link opens a web page, not a PDF or picture.");
  let filename = nameFromDisposition(response.headers.get("content-disposition")) || nameFromUrl(url);
  if (!A.ACCEPTED.test(filename)) {
    if (!MIME_EXT[type]) {
      throw new Error(`ScanToDoc reads PDFs and pictures (PNG, JPG, TIFF, WebP, GIF, BMP); this is ${type || "an unknown kind of file"}.`);
    }
    filename = filename.replace(/\.[a-z0-9]{1,5}$/i, "") + MIME_EXT[type];
  }
  return { blob: await response.blob(), filename };
}

export function nameFromUrl(url) {
  try {
    const u = new URL(url);
    if (u.protocol === "data:") return "picture";
    const last = decodeURIComponent(u.pathname.split("/").filter(Boolean).pop() || u.hostname);
    return last.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 120) || "document";
  } catch {
    return "document";
  }
}

function nameFromDisposition(header) {
  if (!header) return "";
  const star = /filename\*\s*=\s*[^']*''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : "";
}

// ---------------------------------------------------------------- notices

async function notify(id, title, message) {
  try {
    await chrome.notifications.create(id, {
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon128.png"),
      title,
      message,
    });
  } catch {
    /* notifications may be turned off */
  }
}

export async function showResult(id) {
  const job = await getJob(id);
  if (job && job.downloadId != null) {
    try {
      await chrome.downloads.show(job.downloadId);
      return;
    } catch {
      /* the file was moved or deleted */
    }
  }
  if (job && job.pid) await chrome.tabs.create({ url: await A.appUrl(job.pid) });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
