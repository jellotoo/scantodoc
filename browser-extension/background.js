// The extension's background worker: right-click menus, messages from the
// popup and the convert page, and the conversions themselves (lib/jobs.js).

import * as jobs from "./lib/jobs.js";

const MENU_TITLES = {
  link: "Convert linked PDF or picture with ScanToDoc",
  image: "Convert this picture with ScanToDoc",
  page: "Convert this PDF with ScanToDoc",
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "link", title: MENU_TITLES.link, contexts: ["link"] });
    chrome.contextMenus.create({ id: "image", title: MENU_TITLES.image, contexts: ["image"] });
    chrome.contextMenus.create({
      id: "page",
      title: MENU_TITLES.page,
      contexts: ["page", "frame"],
      documentUrlPatterns: ["*://*/*.pdf", "*://*/*.pdf?*", "*://*/*.PDF", "*://*/*.PDF?*"],
    });
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  const url =
    info.menuItemId === "link" ? info.linkUrl : info.menuItemId === "image" ? info.srcUrl : info.frameUrl || info.pageUrl;
  if (url) jobs.startFromUrl(url);
});

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  const handle = {
    convertUrl: () => jobs.startFromUrl(message.url),
    track: () => jobs.startFromProject(message.pid, message.name, message.options),
    retry: () => jobs.retry(message.id),
    stop: () => jobs.stop(message.id),
    remove: () => jobs.removeJob(message.id),
    clearFinished: () => jobs.clearFinished(),
    show: () => jobs.showResult(message.id),
  }[message.type];
  if (!handle) return false;
  Promise.resolve(handle()).then(
    (result) => reply({ ok: true, result }),
    (err) => reply({ ok: false, error: String(err.message || err) }),
  );
  return true; // reply asynchronously
});

chrome.notifications.onClicked.addListener((id) => {
  jobs.showResult(id);
  chrome.notifications.clear(id);
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "resume") jobs.resumeAll();
});

// The worker may have been stopped in the middle of a conversion.
jobs.resumeAll();
