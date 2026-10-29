import { useEffect, useState } from "react";
import { Cpu, Sparkles, Layers, AlertTriangle } from "lucide-react";
import { api, P, usd } from "../api.js";
import { Button, Field, Modal, Select, Spinner, Toggle, cx } from "./ui.jsx";

const READERS = [
  {
    id: "local",
    icon: Cpu,
    title: "Local (free)",
    text: "Reads the pages on this computer with Tesseract OCR. Free, private, works offline. Good for clean printed pages.",
  },
  {
    id: "hybrid",
    icon: Layers,
    title: "Hybrid",
    text: "Local first; only pages the local reader finds hard (multi-column, low confidence) go to Claude. Saves money.",
  },
  {
    id: "claude",
    icon: Sparkles,
    title: "Claude (best)",
    text: "Every page is read by Claude's vision. Most accurate for formatting, tables, nikud and complex layouts. Costs a little per page.",
  },
];

const LANG_NAMES = { eng: "English", heb: "Hebrew", yid: "Yiddish", ara: "Arabic", deu: "German", fra: "French", rus: "Russian", spa: "Spanish" };

export default function ConvertDialog({ project, config, onStart, onClose, openSettings }) {
  const prev = project.settings || {};
  const hasDoc = !!project.document?.pages?.length;
  const [reader, setReader] = useState(prev.reader || "local");
  const [model, setModel] = useState(prev.model || config?.default_model || "claude-haiku-5-5");
  const [langs, setLangs] = useState(() => (prev.languages || "eng+heb").split("+"));
  const [pages, setPages] = useState(prev.pages || "");
  const [force, setForce] = useState(false);
  const [est, setEst] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const available = (config?.languages || []).filter((l) => l !== "osd");
  const needsKey = reader !== "local" && !config?.has_api_key;
  const needsTess = reader !== "claude" && config && !config.tesseract;

  const body = { reader, model, languages: langs.join("+") || "eng", pages: pages.trim() || null, force };
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api
        .post(`${P(project.id)}/estimate`, body)
        .then((r) => live && (setEst(r), setError("")))
        .catch((e) => live && setError(e.message));
    }, 200);
    return () => {
      live = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reader, model, pages, project.id]);

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post(`${P(project.id)}/convert`, body);
      onStart();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <Modal
      wide
      title={hasDoc ? "Read the pages again" : "Convert to an editable document"}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={start} disabled={busy || needsKey || needsTess} data-testid="start-convert">
            {busy && <Spinner size={14} />} Start
          </Button>
        </>
      }
    >
      <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Reader">
        {READERS.map((r) => (
          <button
            key={r.id}
            role="radio"
            aria-checked={reader === r.id}
            onClick={() => setReader(r.id)}
            className={cx(
              "rounded-lg border p-3 text-left transition-colors",
              reader === r.id
                ? "border-indigo-500 bg-indigo-50 ring-2 ring-indigo-500/20 dark:bg-indigo-500/10"
                : "border-stone-200 hover:border-stone-300 dark:border-stone-700 dark:hover:border-stone-600",
            )}
          >
            <span className="flex items-center gap-2 text-sm font-semibold">
              <r.icon size={16} className="text-indigo-600 dark:text-indigo-400" /> {r.title}
            </span>
            <span className="mt-1 block text-xs leading-snug text-stone-600 dark:text-stone-400">{r.text}</span>
          </button>
        ))}
      </div>

      {needsKey && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            This reader needs a Claude API key.{" "}
            <button className="font-semibold underline" onClick={openSettings}>
              Add one in Settings
            </button>
            , or choose the free local reader.
          </span>
        </div>
      )}
      {needsTess && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>Tesseract OCR is not installed, so the local reader cannot run. See “Install Tesseract” in the README, or use Claude.</span>
        </div>
      )}

      <div className="mt-4 grid gap-x-4 sm:grid-cols-2">
        {reader !== "local" && (
          <Field label="Claude model">
            <Select
              value={model}
              onChange={setModel}
              options={(config?.models || []).map((m) => [m.id, `${m.label} ($${m.input}/$${m.output} per M tokens)`])}
            />
          </Field>
        )}
        {reader !== "claude" && available.length > 0 && (
          <Field label="Languages on the pages (local reader)">
            <div className="flex flex-wrap gap-x-3 gap-y-1 pt-1">
              {available.map((l) => (
                <label key={l} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={langs.includes(l)}
                    onChange={(e) => setLangs(e.target.checked ? [...langs, l] : langs.filter((x) => x !== l))}
                  />
                  {LANG_NAMES[l] || l}
                </label>
              ))}
            </div>
          </Field>
        )}
        <Field label="Pages" hint={`Leave empty for all ${project.source_pages || ""} pages, or e.g. 1-10, 15`}>
          <input className="field" value={pages} onChange={(e) => setPages(e.target.value)} placeholder="All pages" />
        </Field>
      </div>
      {hasDoc && (
        <Toggle
          label="Read pages that are already done again"
          hint="Otherwise only new or failed pages are read. Your corrections on re-read pages are replaced."
          checked={force}
          onChange={setForce}
        />
      )}

      <div className="mt-3 rounded-lg bg-stone-100 p-3 text-sm dark:bg-stone-800" data-testid="estimate">
        {error ? (
          <span className="text-red-600 dark:text-red-400">{error}</span>
        ) : !est ? (
          <Spinner />
        ) : reader === "local" ? (
          <span>
            <b>{est.pages}</b> page{est.pages === 1 ? "" : "s"} · <b>Free</b> — nothing leaves this computer.
          </span>
        ) : (
          <span>
            <b>{est.pages}</b> page{est.pages === 1 ? "" : "s"} · estimated cost{" "}
            <b>
              {est.upper_bound ? "up to " : "about "}
              {usd(est.typical)}
            </b>{" "}
            <span className="text-stone-500">
              (range {usd(est.low)}–{usd(est.high)}; {usd(est.per_page)} per page)
            </span>
            {est.upper_bound && <span className="block text-xs text-stone-500">Hybrid only pays for the pages that are sent to Claude.</span>}
          </span>
        )}
      </div>
    </Modal>
  );
}
