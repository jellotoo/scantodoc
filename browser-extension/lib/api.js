// Talking to ScanToDoc running on this computer (started with the start file or
// `scantodoc serve`). The free extension only ever asks for local readings.

export const DEFAULTS = {
  port: 8765,
  format: "docx",
  preset: "keep-original",
  languages: ["eng", "heb"],
};

export const FORMATS = [
  ["docx", "Word (.docx)"],
  ["pdf", "PDF"],
  ["html", "Web page (.html)"],
  ["md", "Markdown (.md)"],
  ["txt", "Text (.txt)"],
];

export const LANGUAGES = [
  ["eng", "English"],
  ["heb", "Hebrew"],
  ["yid", "Yiddish"],
];

export const ACCEPTED = /\.(pdf|png|jpe?g|tiff?|webp|gif|bmp)$/i;

export class ServerDown extends Error {
  constructor() {
    super("ScanToDoc isn't running on this computer. Start it (double-click start-windows.bat or start-mac.command), then try again.");
    this.name = "ServerDown";
  }
}

export async function getSettings() {
  const { settings } = await chrome.storage.sync.get("settings");
  return { ...DEFAULTS, ...(settings || {}) };
}

export async function saveSettings(changes) {
  const settings = { ...(await getSettings()), ...changes };
  await chrome.storage.sync.set({ settings });
  return settings;
}

export async function baseUrl() {
  const { port } = await getSettings();
  return `http://127.0.0.1:${port}`;
}

export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch((await baseUrl()) + path, options);
  } catch {
    throw new ServerDown();
  }
  if (!response.ok) {
    let detail = `ScanToDoc answered ${response.status}.`;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return response.json();
}

const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const getConfig = () => api("/api/config");
export const getPresets = () => api("/api/presets");
export const getProgress = (pid) => api(`/api/projects/${encodeURIComponent(pid)}/progress`);
export const setStyle = (pid, preset) => post(`/api/projects/${encodeURIComponent(pid)}/style`, { preset });
export const cancel = (pid) => post(`/api/projects/${encodeURIComponent(pid)}/cancel`, {});

export function startConvert(pid, { languages, pages }) {
  return post(`/api/projects/${encodeURIComponent(pid)}/convert`, {
    reader: "local",
    languages: (languages && languages.length ? languages : DEFAULTS.languages).join("+"),
    pages: pages || null,
  });
}

/** Upload one or more files (Blob/File with a name) as one new document. */
export function createProject(files, name = "") {
  const form = new FormData();
  for (const { blob, filename } of files) form.append("files", blob, filename);
  if (name) form.append("name", name);
  return api("/api/projects", { method: "POST", body: form });
}

export async function exportUrl(pid, format) {
  return `${await baseUrl()}/api/projects/${encodeURIComponent(pid)}/export/${format}`;
}

export async function appUrl(pid) {
  return `${await baseUrl()}/${pid ? `#/p/${encodeURIComponent(pid)}` : ""}`;
}

/** The languages to read with: the chosen ones that this computer's Tesseract has. */
export function usableLanguages(chosen, installed) {
  const have = new Set(installed || []);
  const usable = (chosen || []).filter((l) => have.has(l));
  return usable.length ? usable : have.has("eng") ? ["eng"] : [...have].slice(0, 1);
}
