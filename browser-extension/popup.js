import * as A from "./lib/api.js";
import { renderJobs, renderOptions, renderStatus, send, watchJobs } from "./lib/ui.js";

const $ = (id) => document.getElementById(id);
const CONVERTIBLE = /\.(pdf|png|jpe?g|tiff?|webp|gif|bmp)([?#].*)?$/i;

async function refresh() {
  const config = await renderStatus($("status"), refresh);
  await renderOptions($("options"), config);
  for (const b of [$("convert-tab"), $("convert-files")]) b.disabled = !config;
}

async function setUpTabButton() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab && tab.url;
  if (!url || !CONVERTIBLE.test(new URL(url).pathname)) return;
  const button = $("convert-tab");
  button.textContent = /\.pdf$/i.test(new URL(url).pathname) ? "Convert this PDF" : "Convert this picture";
  button.classList.remove("hidden");
  button.addEventListener("click", async () => {
    if (url.startsWith("file:")) {
      chrome.tabs.create({ url: chrome.runtime.getURL("convert.html") });
      return;
    }
    button.disabled = true;
    await send({ type: "convertUrl", url });
  });
}

$("convert-files").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("convert.html") });
});

$("toggle-settings").addEventListener("click", (e) => {
  const open = $("settings").classList.toggle("hidden") === false;
  e.currentTarget.setAttribute("aria-expanded", String(open));
});

$("port").addEventListener("change", async (e) => {
  const port = Number(e.target.value);
  if (port >= 1 && port <= 65535) {
    await A.saveSettings({ port });
    refresh();
  }
});

$("open-app").addEventListener("click", async () => chrome.tabs.create({ url: await A.appUrl() }));
$("clear").addEventListener("click", () => send({ type: "clearFinished" }));

A.getSettings().then((s) => ($("port").value = s.port));
watchJobs((jobs) =>
  renderJobs($("jobs"), jobs, {
    emptyText: "Right-click a PDF link or a picture on any web page, or use the buttons above.",
  }),
);
setUpTabButton();
refresh();
