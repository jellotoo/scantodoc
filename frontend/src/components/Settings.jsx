import { useState } from "react";
import { Check, KeyRound, X } from "lucide-react";
import { api } from "../api.js";
import { Button, Field, Modal, Segmented, useToast } from "./ui.jsx";

function Status({ ok, children }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {ok ? <Check size={16} className="mt-0.5 text-emerald-600" /> : <X size={16} className="mt-0.5 text-red-500" />}
      <span>{children}</span>
    </li>
  );
}

export default function Settings({ config, theme, setTheme, onChanged, onClose }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const save = async () => {
    setBusy(true);
    try {
      await api.post("/api/key", { key });
      setKey("");
      toast("API key saved on this computer.");
      onChanged();
    } catch (e) {
      toast(e.message, { kind: "error" });
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    try {
      const r = await api.del("/api/key");
      toast(r.has_api_key ? "Removed from the settings file, but ANTHROPIC_API_KEY is still set in your environment." : "API key removed.");
      onChanged();
    } catch (e) {
      toast(e.message, { kind: "error" });
    }
  };

  return (
    <Modal title="Settings" onClose={onClose} footer={<Button onClick={onClose}>Done</Button>}>
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <KeyRound size={16} /> Claude API key
        </h3>
        <p className="text-sm text-stone-600 dark:text-stone-400">
          Only needed for the <b>Claude</b> and <b>Hybrid</b> readers. The free local reader works without it. The key is saved in{" "}
          <code className="rounded bg-stone-100 px-1 text-xs dark:bg-stone-800">{config?.home}/.env</code> on this computer and is never
          shown in or sent to the browser.
        </p>
        <p className="text-sm" data-testid="key-status">
          Status:{" "}
          {config?.has_api_key ? (
            <span className="font-medium text-emerald-700 dark:text-emerald-400">a key is set ✓</span>
          ) : (
            <span className="font-medium text-stone-500">no key</span>
          )}
        </p>
        <div className="flex gap-2">
          <input
            type="password"
            autoComplete="off"
            className="field"
            placeholder="sk-ant-…"
            aria-label="Claude API key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <Button variant="primary" disabled={!key.trim() || busy} onClick={save}>
            Save
          </Button>
        </div>
        {config?.has_api_key && (
          <button className="text-sm text-red-600 hover:underline" onClick={remove}>
            Remove the saved key
          </button>
        )}
        <p className="text-xs text-stone-500">
          Get a key at platform.claude.com → API keys. Usage is billed to that account; ScanToDoc shows an estimate before anything is sent.
        </p>
      </section>

      <section className="mt-6 space-y-2">
        <h3 className="text-sm font-semibold">Appearance</h3>
        <Segmented
          value={theme}
          onChange={setTheme}
          options={[
            ["system", "Match computer"],
            ["light", "Light"],
            ["dark", "Dark"],
          ]}
        />
      </section>

      <section className="mt-6 space-y-2">
        <h3 className="text-sm font-semibold">This computer</h3>
        <ul className="space-y-1.5">
          <Status ok={config?.tesseract}>
            Local reader (Tesseract OCR):{" "}
            {config?.tesseract ? `${config.tesseract_version}; languages ${config.languages.filter((l) => l !== "osd").join(", ")}` : "not installed — see the README"}
          </Status>
          <Status ok={config?.chromium}>PDF export (Chromium or Edge): {config?.chromium ? "available" : "not found — run `playwright install chromium`"}</Status>
          <Status ok={config?.has_api_key}>Claude reader: {config?.has_api_key ? "ready" : "add an API key above"}</Status>
        </ul>
        <Field label="Version">
          <span className="text-sm">ScanToDoc {config?.version}</span>
        </Field>
      </section>
    </Modal>
  );
}
