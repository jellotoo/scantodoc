import { useEffect, useState } from "react";
import {
  AlignLeft,
  Bold,
  BookMarked,
  Palette,
  Ruler,
  Settings2,
  Sparkles,
  Type,
  FileType2,
  Save,
  Trash2,
  RotateCcw,
} from "lucide-react";
import { api } from "../api.js";
import { getPath, setPath, ELEMENTS } from "../styleutil.js";
import { Button, ColorInput, Field, Modal, NumberInput, Section, Segmented, Select, Toggle, useToast } from "./ui.jsx";

// A font box: type any font name, or pick from the curated suggestions.
function FontInput({ value, onChange, script, fonts, label, placeholder = "Keep original" }) {
  const id = `fonts-${script}`;
  return (
    <Field label={label}>
      <input
        className="field"
        list={id}
        value={value || ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value.trim() ? e.target.value : null)}
        dir={script === "hebrew" ? "auto" : "ltr"}
      />
      <datalist id={id}>
        {fonts
          .filter((f) => (script === "hebrew" ? f.script !== "latin" : f.script !== "hebrew"))
          .map((f) => (
            <option key={f.name} value={f.name}>
              {f.source}
            </option>
          ))}
      </datalist>
    </Field>
  );
}

function FontPair({ path, style, set, fonts, title }) {
  return (
    <div className="mt-2">
      {title && <p className="text-xs font-semibold text-stone-500 uppercase">{title}</p>}
      <div className="grid grid-cols-2 gap-2">
        <FontInput label="English / Latin" script="latin" fonts={fonts} value={getPath(style, `${path}.latin`)} onChange={(v) => set(`${path}.latin`, v)} />
        <FontInput label="Hebrew / Yiddish" script="hebrew" fonts={fonts} value={getPath(style, `${path}.hebrew`)} onChange={(v) => set(`${path}.hebrew`, v)} />
      </div>
    </div>
  );
}

function PresetBar({ style, onApply, presets, reloadPresets }) {
  const [chosen, setChosen] = useState("");
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const toast = useToast();
  const apply = async (key) => {
    setChosen(key);
    if (!key) return;
    try {
      onApply(await api.get(`/api/presets/${encodeURIComponent(key)}`));
    } catch (e) {
      toast(e.message, { kind: "error" });
    }
  };
  const save = async () => {
    try {
      await api.post("/api/presets", { name, description: desc, style });
      setSaving(false);
      toast(`Saved preset “${name}”.`);
      reloadPresets();
    } catch (e) {
      toast(e.message, { kind: "error" });
    }
  };
  const chosenPreset = presets.find((p) => p.key === chosen);
  const remove = async () => {
    if (!chosenPreset || chosenPreset.builtin || !confirm(`Delete the preset “${chosenPreset.name}”?`)) return;
    await api.del(`/api/presets/${encodeURIComponent(chosen)}`);
    setChosen("");
    reloadPresets();
  };
  return (
    <div className="border-b border-stone-200 px-4 py-3 dark:border-stone-800">
      <label className="mb-1 block text-xs font-medium text-stone-600 dark:text-stone-400" htmlFor="preset-select">
        Preset
      </label>
      <div className="flex gap-1.5">
        <select id="preset-select" className="field" value={chosen} onChange={(e) => apply(e.target.value)} data-testid="preset-select">
          <option value="">Choose a preset…</option>
          <optgroup label="Built in">
            {presets.filter((p) => p.builtin).map((p) => (
              <option key={p.key} value={p.key}>
                {p.name}
              </option>
            ))}
          </optgroup>
          {presets.some((p) => !p.builtin) && (
            <optgroup label="Saved">
              {presets.filter((p) => !p.builtin).map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <Button size="md" title="Save these settings as a preset" onClick={() => (setName(style.name || ""), setSaving(true))}>
          <Save size={15} />
        </Button>
        {chosenPreset && !chosenPreset.builtin && (
          <Button size="md" title="Delete this saved preset" onClick={remove}>
            <Trash2 size={15} />
          </Button>
        )}
      </div>
      {chosenPreset?.description && <p className="mt-1 text-xs text-stone-500">{chosenPreset.description}</p>}
      {saving && (
        <Modal
          title="Save as preset"
          onClose={() => setSaving(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setSaving(false)}>
                Cancel
              </Button>
              <Button variant="primary" disabled={!name.trim()} onClick={save}>
                Save preset
              </Button>
            </>
          }
        >
          <Field label="Name">
            <input className="field" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="My book style" />
          </Field>
          <Field label="Description (optional)">
            <input className="field" value={desc} onChange={(e) => setDesc(e.target.value)} />
          </Field>
          <p className="mt-2 text-xs text-stone-500">Presets are saved as JSON files in your ScanToDoc folder and can be used from the command line too.</p>
        </Modal>
      )}
    </div>
  );
}

export default function StylePanel({ style, onChange, fonts, presets, reloadPresets, hasRtl }) {
  const set = (path, value) => onChange(setPath(style, path, value));
  const g = (path) => getPath(style, path);
  const [perElement, setPerElement] = useState(false);
  useEffect(() => {
    if (Object.keys(style.fonts?.elements || {}).length) setPerElement(true);
  }, [style.fonts?.elements]);

  const sizes = style.sizes || {};
  const colors = style.colors || {};
  const page = style.page || {};
  const ex = style.extras || {};

  return (
    <div className="text-sm" data-testid="style-panel">
      <PresetBar style={style} onApply={onChange} presets={presets} reloadPresets={reloadPresets} />
      <div className="flex justify-end px-4 pt-2">
        <button className="flex items-center gap-1 text-xs text-stone-500 hover:text-indigo-600" onClick={() => onChange({})} title="Back to the original look">
          <RotateCcw size={12} /> Reset to original
        </button>
      </div>

      <Section title="Fonts" icon={Type} defaultOpen>
        <FontPair title="Whole document" path="fonts.body" style={style} set={set} fonts={fonts} />
        <FontPair title="Headings" path="fonts.headings" style={style} set={set} fonts={fonts} />
        <Toggle label="Different fonts for headings 1–4, lists, tables, captions…" checked={perElement} onChange={setPerElement} />
        {perElement &&
          ELEMENTS.filter(([k]) => k !== "body").map(([k, label]) => (
            <FontPair key={k} title={label} path={`fonts.elements.${k}`} style={style} set={set} fonts={fonts} />
          ))}
        <p className="mt-2 text-xs text-stone-500">
          Word uses a font only if it is installed on the reader's computer. HTML and PDF exports include free look-alike fonts.
        </p>
      </Section>

      <Section title="Sizes" icon={FileType2} badge={sizes.mode && sizes.mode !== "keep" ? sizes.mode : null}>
        <Segmented
          value={sizes.mode || "keep"}
          onChange={(v) => set("sizes.mode", v)}
          options={[
            ["keep", "As scanned"],
            ["scale", "Scale"],
            ["exact", "Exact"],
          ]}
        />
        {sizes.mode === "scale" && (
          <Field label={`Scale: ${sizes.scale ?? 100}%`} className="mt-2">
            <input
              type="range"
              min={50}
              max={200}
              step={5}
              className="w-full accent-indigo-600"
              value={sizes.scale ?? 100}
              onChange={(e) => set("sizes.scale", Number(e.target.value))}
            />
          </Field>
        )}
        {sizes.mode === "exact" && (
          <div className="mt-2 grid grid-cols-2 gap-x-2">
            {ELEMENTS.map(([k, label]) => (
              <Field key={k} label={`${label} (pt)`}>
                <NumberInput value={sizes.exact?.[k]} step={0.5} min={4} max={96} onChange={(v) => set(`sizes.exact.${k}`, v ?? undefined)} />
              </Field>
            ))}
          </div>
        )}
      </Section>

      <Section title="Colours" icon={Palette} badge={colors.mode && colors.mode !== "keep" ? colors.mode : null}>
        <Segmented
          value={colors.mode || "keep"}
          onChange={(v) => set("colors.mode", v)}
          options={[
            ["keep", "As scanned"],
            ["black", "All black"],
            ["custom", "Custom"],
          ]}
        />
        {colors.mode === "custom" && (
          <div className="mt-2">
            {ELEMENTS.map(([k, label]) => (
              <ColorInput key={k} label={label} value={colors.custom?.[k]} onChange={(v) => set(`colors.custom.${k}`, v ?? undefined)} />
            ))}
          </div>
        )}
        <div className="mt-3 border-t border-stone-200 pt-2 dark:border-stone-800">
          <ColorInput label="Links" value={colors.link} onChange={(v) => set("colors.link", v)} keepLabel="Default" />
          <ColorInput label="Page background" value={colors.page_background} onChange={(v) => set("colors.page_background", v)} keepLabel="White" />
          <ColorInput label="Accent (heading lines)" value={colors.accent} onChange={(v) => set("colors.accent", v)} keepLabel="None" />
          {colors.accent && (
            <Field label="Accent style">
              <Select
                value={colors.accent_style || "none"}
                onChange={(v) => set("colors.accent_style", v)}
                options={[
                  ["none", "None"],
                  ["underline", "Thick line under headings"],
                  ["rule", "Thin rule under headings"],
                  ["bar", "Bar beside headings"],
                ]}
              />
            </Field>
          )}
        </div>
      </Section>

      <Section title="Bold, italic and emphasis" icon={Bold}>
        <Toggle label="Keep bold" checked={g("emphasis.bold") ?? true} onChange={(v) => set("emphasis.bold", v)} />
        <Toggle label="Keep italic" checked={g("emphasis.italic") ?? true} onChange={(v) => set("emphasis.italic", v)} />
        <Toggle label="Keep underline" checked={g("emphasis.underline") ?? true} onChange={(v) => set("emphasis.underline", v)} />
        <Toggle label="Keep strikethrough" checked={g("emphasis.strike") ?? true} onChange={(v) => set("emphasis.strike", v)} />
        <Toggle
          label="Turn short bold lines into headings"
          hint="Useful when the scan used bold text instead of real headings."
          checked={!!g("emphasis.bold_lines_to_headings")}
          onChange={(v) => set("emphasis.bold_lines_to_headings", v)}
        />
        {g("emphasis.bold_lines_to_headings") && (
          <Field label="as heading level">
            <Select
              value={String(g("emphasis.bold_line_heading_level") ?? 3)}
              onChange={(v) => set("emphasis.bold_line_heading_level", Number(v))}
              options={[1, 2, 3, 4].map((n) => [String(n), `Heading ${n}`])}
            />
          </Field>
        )}
      </Section>

      <Section title="Spacing" icon={Ruler}>
        <div className="grid grid-cols-2 gap-x-2">
          <Field label="Line spacing" hint="1 = single, 1.5, 2 = double">
            <NumberInput value={g("spacing.line_spacing")} step={0.05} min={0.8} max={3} placeholder="Auto" onChange={(v) => set("spacing.line_spacing", v)} />
          </Field>
          <Field label="First-line indent (pt)">
            <NumberInput value={g("spacing.first_line_indent")} step={1} min={0} max={72} onChange={(v) => set("spacing.first_line_indent", v)} />
          </Field>
          <Field label="Space before paragraphs (pt)">
            <NumberInput value={g("spacing.space_before")} step={1} min={0} max={72} onChange={(v) => set("spacing.space_before", v)} />
          </Field>
          <Field label="Space after paragraphs (pt)">
            <NumberInput value={g("spacing.space_after")} step={1} min={0} max={72} onChange={(v) => set("spacing.space_after", v)} />
          </Field>
        </div>
      </Section>

      <Section title="Page" icon={BookMarked}>
        <div className="grid grid-cols-2 gap-x-2">
          <Field label="Paper size">
            <Select
              value={page.size || "keep"}
              onChange={(v) => set("page.size", v)}
              options={[
                ["keep", "As scanned"],
                ["letter", "Letter"],
                ["a4", "A4"],
                ["legal", "Legal"],
                ["a5", "A5"],
                ["custom", "Custom"],
              ]}
            />
          </Field>
          <Field label="Orientation">
            <Select
              value={page.orientation || "portrait"}
              onChange={(v) => set("page.orientation", v)}
              options={[
                ["portrait", "Portrait"],
                ["landscape", "Landscape"],
              ]}
            />
          </Field>
          {page.size === "custom" && (
            <>
              <Field label="Width (inches)">
                <NumberInput value={page.width_in ?? 8.5} step={0.1} min={2} max={30} onChange={(v) => set("page.width_in", v ?? 8.5)} />
              </Field>
              <Field label="Height (inches)">
                <NumberInput value={page.height_in ?? 11} step={0.1} min={2} max={30} onChange={(v) => set("page.height_in", v ?? 11)} />
              </Field>
            </>
          )}
          {["top", "bottom", "left", "right"].map((side) => (
            <Field key={side} label={`${side[0].toUpperCase() + side.slice(1)} margin (in)`}>
              <NumberInput
                value={page.margins?.[side] ?? 1}
                step={0.05}
                min={0}
                max={4}
                placeholder="1"
                onChange={(v) => set(`page.margins.${side}`, v ?? 1)}
              />
            </Field>
          ))}
        </div>
        <Field label="Text columns">
          <Segmented
            value={String(page.columns || 1)}
            onChange={(v) => set("page.columns", Number(v))}
            options={[
              ["1", "One"],
              ["2", "Two"],
            ]}
          />
        </Field>
      </Section>

      <Section title="Alignment" icon={AlignLeft} badge={g("alignment.mode") && g("alignment.mode") !== "keep" ? g("alignment.mode") : null}>
        <Select
          value={g("alignment.mode") || "keep"}
          onChange={(v) => set("alignment.mode", v)}
          options={[
            ["keep", "As scanned"],
            ["start", hasRtl ? "Start of line (right for Hebrew, left for English)" : "Start of line"],
            ["left", "Left"],
            ["right", "Right"],
            ["justify", "Justified"],
          ]}
        />
        <Toggle label="Also align headings this way" checked={!!g("alignment.headings")} onChange={(v) => set("alignment.headings", v)} />
      </Section>

      <Section title="Extras" icon={Sparkles}>
        <Toggle label="Table of contents" checked={!!ex.toc} onChange={(v) => set("extras.toc", v)} />
        {ex.toc && (
          <Field label="Contents title">
            <input className="field" value={ex.toc_title ?? "Contents"} onChange={(e) => set("extras.toc_title", e.target.value)} />
          </Field>
        )}
        <Toggle label="Page numbers" checked={!!ex.page_numbers} onChange={(v) => set("extras.page_numbers", v)} />
        {ex.page_numbers && (
          <Segmented
            value={ex.page_number_align || "center"}
            onChange={(v) => set("extras.page_number_align", v)}
            options={[
              ["left", "Left"],
              ["center", "Centre"],
              ["right", "Right"],
            ]}
          />
        )}
        <Toggle label="Title page" checked={!!ex.title_page} onChange={(v) => set("extras.title_page", v)} />
        {ex.title_page && (
          <>
            <Field label="Title" hint="Empty = the first heading">
              <input className="field" dir="auto" value={ex.title || ""} onChange={(e) => set("extras.title", e.target.value)} />
            </Field>
            <Field label="Subtitle">
              <input className="field" dir="auto" value={ex.subtitle || ""} onChange={(e) => set("extras.subtitle", e.target.value)} />
            </Field>
            <Field label="Author">
              <input className="field" dir="auto" value={ex.author || ""} onChange={(e) => set("extras.author", e.target.value)} />
            </Field>
          </>
        )}
      </Section>

      <Section title="Advanced" icon={Settings2}>
        <Toggle
          label="Keep running heads and feet"
          hint="Book titles or chapter names repeated at the top/bottom of each scanned page."
          checked={!!ex.keep_headers_footers}
          onChange={(v) => set("extras.keep_headers_footers", v)}
        />
        <Toggle label="Keep the scan's printed page numbers" checked={!!ex.keep_page_numbers} onChange={(v) => set("extras.keep_page_numbers", v)} />
        <Toggle
          label="Join paragraphs split across pages"
          checked={ex.merge_across_pages ?? true}
          onChange={(v) => set("extras.merge_across_pages", v)}
        />
        <Toggle label="Include pictures" checked={ex.include_figures ?? true} onChange={(v) => set("extras.include_figures", v)} />
        <Toggle label="Remove nikud (vowel points)" checked={!!ex.strip_nikud} onChange={(v) => set("extras.strip_nikud", v)} />
        <Toggle label="Remove ta'amim (cantillation marks)" checked={!!ex.strip_teamim} onChange={(v) => set("extras.strip_teamim", v)} />
        <Toggle label="Make web addresses clickable" checked={ex.link_urls ?? true} onChange={(v) => set("extras.link_urls", v)} />
        <Toggle
          label="Mark unsure words in exports"
          hint="Yellow highlight in Word/HTML/PDF, for proofreading."
          checked={!!ex.highlight_uncertain}
          onChange={(v) => set("extras.highlight_uncertain", v)}
        />
        <Field label="Pages with several text areas (e.g. Gemara with Rashi)">
          <Select
            value={ex.regions || "per_page"}
            onChange={(v) => set("extras.regions", v)}
            options={[
              ["per_page", "Page by page, each area labelled"],
              ["grouped", "Main text first, then each commentary"],
              ["main_only", "Main text only"],
            ]}
          />
        </Field>
      </Section>
    </div>
  );
}
