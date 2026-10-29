import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, FolderOpen, Trash2, FileText } from "lucide-react";
import { api, go, P, pageImage, usd } from "../api.js";
import { Button, IconButton, Spinner, cx, useToast } from "./ui.jsx";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.gif";
const OK_EXT = /\.(pdf|png|jpe?g|tiff?|bmp|webp|gif)$/i;

export const STATUS = {
  new: ["Not converted yet", "bg-stone-200 text-stone-700 dark:bg-stone-700 dark:text-stone-200"],
  converting: ["Converting…", "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"],
  done: ["Ready", "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"],
  partial: ["Some pages failed", "bg-orange-100 text-orange-800 dark:bg-orange-500/20 dark:text-orange-300"],
  error: ["Failed", "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300"],
  cancelled: ["Stopped", "bg-stone-200 text-stone-700 dark:bg-stone-700 dark:text-stone-200"],
  interrupted: ["Interrupted", "bg-stone-200 text-stone-700 dark:bg-stone-700 dark:text-stone-200"],
};

export function StatusChip({ status }) {
  const [label, cls] = STATUS[status] || [status, STATUS.new[1]];
  return <span className={cx("inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium", cls)}>{label}</span>;
}

// Walk a dropped folder (Chrome/Edge/Firefox/Safari all support webkitGetAsEntry).
async function filesFromDrop(dt) {
  const items = [...(dt.items || [])].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (!items.length) return [...dt.files];
  const out = [];
  const readEntry = (entry) =>
    new Promise((resolve) => {
      if (entry.isFile) entry.file((f) => (out.push(f), resolve()), resolve);
      else if (entry.isDirectory) {
        const reader = entry.createReader();
        const all = [];
        const next = () =>
          reader.readEntries(async (batch) => {
            if (!batch.length) {
              for (const e of all) await readEntry(e);
              resolve();
            } else {
              all.push(...batch);
              next();
            }
          }, resolve);
        next();
      } else resolve();
    });
  for (const e of items) await readEntry(e);
  return out;
}

export function DropZone({ onFiles, busy }) {
  const [over, setOver] = useState(false);
  const fileRef = useRef(null);
  const folderRef = useRef(null);
  const pick = (list) => {
    const files = [...list].filter((f) => OK_EXT.test(f.name));
    if (files.length) onFiles(files);
  };
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={async (e) => {
        e.preventDefault();
        setOver(false);
        pick(await filesFromDrop(e.dataTransfer));
      }}
      className={cx(
        "flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
        over
          ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10"
          : "border-stone-300 bg-white dark:border-stone-700 dark:bg-stone-900",
      )}
      data-testid="dropzone"
    >
      {busy ? (
        <>
          <Spinner size={28} className="text-indigo-600" />
          <p className="text-sm text-stone-600 dark:text-stone-300">Uploading…</p>
        </>
      ) : (
        <>
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
            <FileUp size={24} />
          </span>
          <div>
            <p className="text-base font-semibold">Drop scanned PDFs or page images here</p>
            <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
              PDF, PNG, JPG or TIFF. Several images or a whole folder become one document, in name order.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <Button variant="primary" onClick={() => fileRef.current.click()}>
              <FileUp size={16} /> Choose files
            </Button>
            <Button onClick={() => folderRef.current.click()}>
              <FolderOpen size={16} /> Choose a folder
            </Button>
          </div>
          <input ref={fileRef} type="file" multiple accept={ACCEPT} className="hidden" data-testid="file-input" onChange={(e) => pick(e.target.files)} />
          <input ref={folderRef} type="file" webkitdirectory="" className="hidden" onChange={(e) => pick(e.target.files)} />
        </>
      )}
    </div>
  );
}

export default function ProjectsList() {
  const [projects, setProjects] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(() => api.get("/api/projects").then(setProjects).catch((e) => toast(e.message, { kind: "error" })), [toast]);
  useEffect(() => {
    load();
  }, [load]);

  const upload = async (files) => {
    setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f, f.name));
      const name = files.length === 1 ? files[0].name.replace(/\.[^.]+$/, "") : (files[0].webkitRelativePath || "").split("/")[0] || files[0].name.replace(/\.[^.]+$/, "");
      fd.append("name", name);
      const p = await api.post("/api/projects", fd);
      go(`/p/${encodeURIComponent(p.id)}?new`);
    } catch (e) {
      toast(e.message, { kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (p) => {
    if (!confirm(`Delete "${p.name}" and all its files? This cannot be undone.`)) return;
    try {
      await api.del(P(p.id));
      load();
    } catch (e) {
      toast(e.message, { kind: "error" });
    }
  };

  return (
    <div className="pane h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:py-10">
        <DropZone onFiles={upload} busy={busy} />
        <h2 className="mt-10 mb-3 text-sm font-semibold uppercase tracking-wide text-stone-500">Your documents</h2>
        {projects === null ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : projects.length === 0 ? (
          <p className="rounded-xl border border-stone-200 bg-white px-4 py-8 text-center text-sm text-stone-500 dark:border-stone-800 dark:bg-stone-900">
            Nothing here yet. Drop a scanned PDF above to start.
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" data-testid="projects">
            {projects.map((p) => (
              <li
                key={p.id}
                className="group relative overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition-shadow hover:shadow-md dark:border-stone-800 dark:bg-stone-900"
              >
                <a href={`#/p/${encodeURIComponent(p.id)}`} className="block">
                  <div className="flex aspect-[4/5] items-center justify-center overflow-hidden bg-stone-100 dark:bg-stone-800">
                    {p.thumbnail ? (
                      <img src={pageImage(p.id, p.thumbnail, 360)} alt="" className="h-full w-full object-cover object-top" loading="lazy" />
                    ) : (
                      <FileText size={40} className="text-stone-300 dark:text-stone-600" />
                    )}
                  </div>
                  <div className="space-y-1 p-3">
                    <p className="truncate text-sm font-medium" title={p.name}>
                      {p.name}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-500 dark:text-stone-400">
                      <StatusChip status={p.status} />
                      <span>
                        {p.page_count} page{p.page_count === 1 ? "" : "s"}
                      </span>
                      {p.cost_usd > 0 && <span>{usd(p.cost_usd)}</span>}
                    </div>
                  </div>
                </a>
                <IconButton
                  title={`Delete ${p.name}`}
                  onClick={() => remove(p)}
                  className="absolute top-2 right-2 bg-white/90 opacity-0 shadow group-hover:opacity-100 focus:opacity-100 dark:bg-stone-900/90"
                >
                  <Trash2 size={15} />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
