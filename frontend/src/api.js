// Small wrappers around the ScanToDoc server API. Every error carries the
// server's plain-language message, ready to show to the user.

async function request(method, url, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, opts);
  } catch {
    throw new Error("Cannot reach ScanToDoc. Is `scantodoc serve` still running?");
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (data.detail) msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body) => request("POST", url, body ?? {}),
  patch: (url, body) => request("PATCH", url, body),
  del: (url) => request("DELETE", url),
};

export const P = (id) => `/api/projects/${encodeURIComponent(id)}`;

export function pageImage(projectId, image, width) {
  const name = image.split("/").pop();
  return `${P(projectId)}/pages/${encodeURIComponent(name)}${width ? `?w=${width}` : ""}`;
}

// Download a file, showing server errors instead of a broken download.
export async function download(url) {
  const res = await request("GET", url);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  let name = "download";
  const star = cd.match(/filename\*=utf-8''([^;]+)/i);
  const plain = cd.match(/filename="?([^";]+)"?/i);
  if (star) name = decodeURIComponent(star[1]);
  else if (plain) name = plain[1];
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  return name;
}

export function usd(x) {
  if (!x) return "$0";
  if (x < 0.01) return `$${x.toFixed(4)}`;
  if (x < 1) return `$${x.toFixed(3)}`;
  return `$${x.toFixed(2)}`;
}

export const go = (path) => {
  window.location.hash = path;
};
