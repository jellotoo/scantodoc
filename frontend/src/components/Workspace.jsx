import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  Check,
  Download,
  Eye,
  Highlighter,
  Italic,
  Link2,
  Paintbrush,
  Pencil,
  Play,
  Square,
  Trash2,
  Underline,
  X,
} from "lucide-react";
import { api, download, P, usd } from "../api.js";
import { BLOCK_CHOICES, blockChoice } from "../styleutil.js";
import { Button, IconButton, Menu, MenuItem, Spinner, cx, useToast } from "./ui.jsx";
import { StatusChip } from "./ProjectsList.jsx";
import ConvertDialog from "./ConvertDialog.jsx";
import ScanPane from "./ScanPane.jsx";
import PreviewPane from "./PreviewPane.jsx";
import StylePanel from "./StylePanel.jsx";

function useNarrow(px = 900) {
  const [narrow, setNarrow] = useState(() => window.innerWidth < px);
  useEffect(() => {
    const mq = matchMedia(`(max-width: ${px - 1}px)`);
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [px]);
  return narrow;
}

function findBlock(doc, id) {
  for (const p of doc?.pages || []) {
    const i = p.blocks.findIndex((b) => b.id === id);
    if (i >= 0) return { page: p, block: p.blocks[i], position: i };
  }
  return null;
}

function Progress({ job, total }) {
  const cells = [];
  for (let i = 0; i < total; i++) cells.push(job.pages[i] || "pending");
  const done = cells.filter((c) => c === "done" || c === "claude" || c === "error").length;
  const label = job.phase === "render" ? `Preparing page images ${job.rendered}/${total}…` : `Reading page ${Math.min(done + 1, total)} of ${total}…`;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2" data-testid="progress">
      <Spinner size={14} className="shrink-0 text-indigo-600" />
      <span className="shrink-0 text-xs text-stone-600 dark:text-stone-300">{label}</span>
      <div className="flex min-w-0 flex-1 gap-0.5 overflow-hidden" aria-hidden="true">
        {cells.map((c, i) => (
          <span
            key={i}
            title={`Page ${i + 1}: ${c}`}
            className={cx(
              "h-2 min-w-[3px] flex-1 rounded-sm",
              c === "done" && "bg-emerald-500",
              c === "claude" && "bg-violet-500",
              c === "error" && "bg-red-500",
              c === "reading" && "animate-pulse bg-amber-400",
              c === "pending" && "bg-stone-300 dark:bg-stone-700",
            )}
          />
        ))}
      </div>
    </div>
  );
}

function BlockBar({ block, editing, onType, onAlign, onDir, onEdit, onSave, onCancel, onDelete, onClose, format }) {
  const keep = (e) => e.preventDefault(); // keep the caret in the text being edited
  const text = block.type !== "table" && block.type !== "figure";
  return (
    <div
      className="flex flex-wrap items-center gap-1 border-b border-stone-200 bg-white px-2 py-1.5 dark:border-stone-800 dark:bg-stone-900"
      data-testid="block-bar"
    >
      {editing ? (
        <>
          <span className="px-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">Editing — Enter saves, Esc cancels</span>
          <IconButton title="Bold (Ctrl+B)" onMouseDown={keep} onClick={() => format("bold")}>
            <Bold size={15} />
          </IconButton>
          <IconButton title="Italic (Ctrl+I)" onMouseDown={keep} onClick={() => format("italic")}>
            <Italic size={15} />
          </IconButton>
          <IconButton title="Underline (Ctrl+U)" onMouseDown={keep} onClick={() => format("underline")}>
            <Underline size={15} />
          </IconButton>
          <span className="flex-1" />
          <Button size="sm" onMouseDown={keep} onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" onMouseDown={keep} onClick={onSave} data-testid="save-edit">
            <Check size={14} /> Save
          </Button>
        </>
      ) : (
        <>
          {text ? (
            <select
              aria-label="Block type"
              className="field h-8 w-auto py-0 text-xs"
              value={blockChoice(block)}
              onChange={(e) => onType(e.target.value)}
              data-testid="block-type"
            >
              {BLOCK_CHOICES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          ) : (
            <span className="px-1 text-xs font-medium capitalize">{block.type}</span>
          )}
          {text && (
            <>
              <span className="mx-1 h-5 w-px bg-stone-200 dark:bg-stone-700" />
              {[
                ["left", AlignLeft],
                ["center", AlignCenter],
                ["right", AlignRight],
                ["justify", AlignJustify],
              ].map(([a, Icon]) => (
                <IconButton key={a} title={`Align ${a}`} active={block.align === a} onClick={() => onAlign(a)}>
                  <Icon size={15} />
                </IconButton>
              ))}
              <button
                className="h-8 rounded-md px-2 text-xs font-semibold text-stone-600 hover:bg-stone-200/70 dark:text-stone-300 dark:hover:bg-stone-800"
                title="Text direction: click to switch between left-to-right and right-to-left"
                onClick={onDir}
              >
                {block.direction === "rtl" ? "RTL ←" : "LTR →"}
              </button>
              <span className="mx-1 h-5 w-px bg-stone-200 dark:bg-stone-700" />
              <Button size="sm" onClick={onEdit} data-testid="edit-text">
                <Pencil size={13} /> Edit text
              </Button>
            </>
          )}
          <IconButton title="Delete this block" onClick={onDelete}>
            <Trash2 size={15} />
          </IconButton>
          <span className="flex-1" />
          <IconButton title="Deselect" onClick={onClose}>
            <X size={15} />
          </IconButton>
        </>
      )}
    </div>
  );
}

export default function Workspace({ id, isNew, config, onTitle, openSettings }) {
  const toast = useToast();
  const narrow = useNarrow();
  const [project, setProject] = useState(null);
  const [doc, setDoc] = useState(null);
  const [style, setStyle] = useState(null);
  const [preview, setPreview] = useState(null);
  const [fonts, setFonts] = useState([]);
  const [presets, setPresets] = useState([]);
  const [job, setJob] = useState(null); // { pages: {i: state}, phase, rendered, total, cost }
  const [showConvert, setShowConvert] = useState(false);
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [showBoxes, setShowBoxes] = useState(true);
  const [highlight, setHighlight] = useState(true);
  const [sync, setSync] = useState(true);
  const [styleOpen, setStyleOpen] = useState(true);
  const [tab, setTab] = useState("result");
  const [rereading, setRereading] = useState(null);
  const scanRef = useRef(null);
  const previewRef = useRef(null);

  // ---------------------------------------------------------------- loading

  const loadProject = useCallback(async () => {
    const p = await api.get(P(id));
    setProject(p);
    setDoc(p.document);
    onTitle(p.name);
    return p;
  }, [id, onTitle]);

  const refreshDoc = useCallback(async () => {
    const p = await api.get(P(id));
    setDoc(p.document);
    setProject((old) => ({ ...(old || {}), ...p }));
  }, [id]);

  useEffect(() => {
    loadProject()
      .then((p) => {
        setStyle(p.style);
        if (p.job?.status === "running") follow();
        else if (isNew || (!p.document && p.status === "new")) setShowConvert(true);
        if (isNew) history.replaceState(null, "", `#/p/${encodeURIComponent(id)}`);
      })
      .catch((e) => toast(e.message, { kind: "error" }));
    api.get("/api/fonts").then((f) => setFonts(f.fonts)).catch(() => {});
    api.get("/api/presets").then(setPresets).catch(() => {});
    return () => onTitle(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // ---------------------------------------------------------------- following a conversion

  const esRef = useRef(null);
  const follow = useCallback(() => {
    esRef.current?.close();
    setJob({ pages: {}, phase: "render", rendered: 0, total: 0, cost: 0 });
    const es = new EventSource(`${P(id)}/events`);
    esRef.current = es;
    let pending = null;
    const refreshSoon = () => {
      if (pending) return;
      pending = setTimeout(() => {
        pending = null;
        refreshDoc().catch(() => {});
      }, 400);
    };
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      setJob((j) => {
        if (!j) return j;
        const pages = { ...j.pages };
        switch (ev.type) {
          case "render":
            return { ...j, phase: "render", rendered: ev.page + 1, total: ev.total };
          case "start":
            return { ...j, phase: "read", total: ev.total };
          case "page_start":
            pages[ev.page] = "reading";
            return { ...j, pages };
          case "page_done":
            pages[ev.page] = ev.reader === "claude" ? "claude" : "done";
            return { ...j, pages, cost: ev.total_cost_usd };
          case "page_error":
            pages[ev.page] = "error";
            return { ...j, pages };
          default:
            return j;
        }
      });
      if (ev.type === "start" || ev.type === "page_done" || ev.type === "page_error") refreshSoon();
      if (ev.type === "page_error") toast(`Page ${ev.page + 1}: ${ev.error}`, { kind: "error" });
      if (ev.type === "error") toast(ev.error, { kind: "error" });
      if (ev.type === "done")
        toast(ev.failed ? `Done, but ${ev.failed} page(s) failed.` : `Done: ${ev.pages} page(s) converted${ev.cost_usd ? ` for ${usd(ev.cost_usd)}` : ""}.`);
    };
    const finish = () => {
      es.close();
      setJob(null);
      refreshDoc().catch(() => {});
    };
    es.addEventListener("end", finish);
    es.addEventListener("idle", finish);
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) finish();
    };
  }, [id, refreshDoc, toast]);
  useEffect(() => () => esRef.current?.close(), []);

  // ---------------------------------------------------------------- preview (re-rendered on every style change)

  const seq = useRef(0);
  useEffect(() => {
    if (!style || !doc) return;
    const n = ++seq.current;
    const t = setTimeout(() => {
      api
        .post(`${P(id)}/preview`, style)
        .then((r) => n === seq.current && setPreview(r))
        .catch((e) => toast(e.message, { kind: "error" }));
    }, 150);
    return () => clearTimeout(t);
  }, [style, doc, id, toast]);

  // ---------------------------------------------------------------- scroll sync

  const lastProgrammatic = useRef({ scan: 0, preview: 0 });
  const sectionsOf = (which) => {
    if (which === "scan") {
      const el = scanRef.current;
      return { el, list: [...(el?.querySelectorAll("section[data-page]") || [])] };
    }
    return { el: previewRef.current?.el, list: previewRef.current?.sections() || [] };
  };
  const syncFrom = (from) => {
    if (!sync || narrow) return;
    if (Date.now() - lastProgrammatic.current[from] < 120) return;
    const to = from === "scan" ? "preview" : "scan";
    const a = sectionsOf(from);
    const b = sectionsOf(to);
    if (!a.el || !b.el || !a.list.length || !b.list.length) return;
    const aTop = a.el.getBoundingClientRect().top;
    const probe = 40;
    let cur = a.list[0];
    for (const s of a.list) if (s.getBoundingClientRect().top - aTop <= probe) cur = s;
    const r = cur.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (probe - (r.top - aTop)) / Math.max(1, r.height)));
    const match = b.list.find((s) => s.dataset.page === cur.dataset.page);
    if (!match) return;
    const bTop = b.el.getBoundingClientRect().top;
    const mr = match.getBoundingClientRect();
    const target = b.el.scrollTop + (mr.top - bTop) + frac * mr.height - probe;
    lastProgrammatic.current[to] = Date.now();
    b.el.scrollTop = target;
  };

  // ---------------------------------------------------------------- selecting and editing blocks

  const select = (bid, from) => {
    if (editingId && bid !== editingId) previewRef.current?.save();
    setSelected(bid);
    if (!bid) return;
    requestAnimationFrame(() => {
      if (from === "scan") {
        const el = previewRef.current?.blockEl(bid);
        if (el) {
          lastProgrammatic.current.preview = Date.now();
          el.scrollIntoView({ block: "center" });
        }
        if (narrow) setTab("result");
      } else {
        const box = scanRef.current?.querySelector(`[data-box="${CSS.escape(bid)}"]`);
        if (box && !narrow) {
          const r = box.getBoundingClientRect();
          const pr = scanRef.current.getBoundingClientRect();
          if (r.top < pr.top || r.bottom > pr.bottom) {
            lastProgrammatic.current.scan = Date.now();
            box.scrollIntoView({ block: "center" });
          }
        }
      }
    });
  };

  const sel = useMemo(() => (selected ? findBlock(doc, selected) : null), [doc, selected]);

  const patchBlock = async (bid, patch) => {
    try {
      const r = await api.patch(`${P(id)}/blocks/${encodeURIComponent(bid)}`, patch);
      setDoc((d) => ({
        ...d,
        pages: d.pages.map((p) => ({ ...p, blocks: p.blocks.map((b) => (b.id === bid ? r.block : b)) })),
      }));
    } catch (e) {
      toast(e.message, { kind: "error" });
    }
  };

  const onType = (choice) => {
    const [type, level] = choice.split(":");
    patchBlock(selected, { type, ...(level ? { level: Number(level) } : {}) });
  };

  const onSaveEdit = (bid, runs, original) => {
    setEditingId(null);
    if (JSON.stringify(runs.map((r) => [r.text, r.bold, r.italic, r.underline])) === JSON.stringify((original || []).map((r) => [r.text, r.bold, r.italic, r.underline])) &&
      runs.every((r, i) => (r.color || null) === (original[i]?.color || null)))
      return;
    patchBlock(bid, { runs });
  };

  const onDelete = async () => {
    const found = findBlock(doc, selected);
    if (!found) return;
    try {
      await api.del(`${P(id)}/blocks/${encodeURIComponent(selected)}`);
      setSelected(null);
      setDoc((d) => ({ ...d, pages: d.pages.map((p) => ({ ...p, blocks: p.blocks.filter((b) => b.id !== found.block.id) })) }));
      toast("Block deleted.", {
        action: {
          label: "Undo",
          run: async () => {
            await api.post(`${P(id)}/blocks/${encodeURIComponent(found.block.id)}/restore`, {
              block: found.block,
              page: found.page.index,
              position: found.position,
            });
            refreshDoc();
          },
        },
        duration: 7000,
      });
    } catch (e) {
      toast(e.message, { kind: "error" });
    }
  };

  const reread = async (index, reader) => {
    setRereading(index);
    try {
      const s = project?.settings || {};
      const r = await api.post(`${P(id)}/pages/${index}/reread`, {
        reader,
        model: s.model || config?.default_model,
        languages: s.languages || "eng+heb",
      });
      setDoc(r.document);
      toast(`Page ${index + 1} read again${reader === "claude" ? " with Claude" : ""}.`);
    } catch (e) {
      toast(e.message, { kind: "error" });
    } finally {
      setRereading(null);
    }
  };

  // Keyboard: Delete removes the selected block, Escape deselects.
  useEffect(() => {
    const on = (e) => {
      if (editingId || !selected || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) return;
      if (e.key === "Escape") setSelected(null);
      if (e.key === "Enter") setEditingId(selected);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [selected, editingId]);

  // ---------------------------------------------------------------- exporting

  const [exporting, setExporting] = useState(null);
  const doExport = async (fmt) => {
    setExporting(fmt);
    try {
      const name = await download(`${P(id)}/export/${fmt}`);
      toast(`Saved ${name} to your Downloads folder.`);
    } catch (e) {
      toast(e.message, { kind: "error" });
    } finally {
      setExporting(null);
    }
  };

  // ---------------------------------------------------------------- layout

  if (!project || !style)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size={24} />
      </div>
    );

  const running = !!job;
  const hasDoc = !!doc?.pages?.length;
  const done = doc?.pages?.some((p) => p.status === "done");
  const cost = running ? job.cost : doc?.usage?.cost_usd || 0;
  const unsure = doc ? doc.pages.reduce((n, p) => n + p.blocks.reduce((m, b) => m + b.runs.filter((r) => r.uncertain).length, 0), 0) : 0;
  const hasRtl = doc?.main_direction === "rtl" || doc?.pages?.some((p) => p.blocks.some((b) => b.direction === "rtl"));

  const scan = (
    <ScanPane
      ref={scanRef}
      projectId={id}
      doc={doc}
      selected={selected}
      hovered={hovered}
      onSelect={select}
      onHover={setHovered}
      showBoxes={showBoxes}
      onScroll={() => syncFrom("scan")}
      onReread={reread}
      rereading={rereading}
      hasKey={config?.has_api_key}
      live={running}
    />
  );
  const result = (
    <div className="flex h-full min-h-0 flex-col">
      {sel && (
        <BlockBar
          block={sel.block}
          editing={editingId === sel.block.id}
          onType={onType}
          onAlign={(a) => patchBlock(selected, { align: a })}
          onDir={() => patchBlock(selected, { direction: sel.block.direction === "rtl" ? "ltr" : "rtl" })}
          onEdit={() => setEditingId(selected)}
          onSave={() => previewRef.current?.save()}
          onCancel={() => previewRef.current?.cancel()}
          onDelete={onDelete}
          onClose={() => setSelected(null)}
          format={(cmd) => previewRef.current?.format(cmd)}
        />
      )}
      <div className="min-h-0 flex-1">
        <PreviewPane
          ref={previewRef}
          preview={preview}
          doc={doc}
          selected={selected}
          hovered={hovered}
          editingId={editingId}
          highlightUnsure={highlight}
          onSelect={select}
          onHover={setHovered}
          onStartEdit={(bid) => {
            const f = findBlock(doc, bid);
            if (f && f.block.type !== "table" && f.block.type !== "figure") {
              setSelected(bid);
              setEditingId(bid);
            }
          }}
          onSaveEdit={onSaveEdit}
          onCancelEdit={() => setEditingId(null)}
          onScroll={() => syncFrom("preview")}
        />
      </div>
    </div>
  );
  const stylePanel = (
    <StylePanel
      style={style}
      onChange={setStyle}
      fonts={fonts}
      presets={presets}
      reloadPresets={() => api.get("/api/presets").then(setPresets)}
      hasRtl={hasRtl}
    />
  );

  return (
    <div className="flex h-full flex-col">
      {/* toolbar */}
      <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-b border-stone-200 bg-white px-3 py-1.5 dark:border-stone-800 dark:bg-stone-900">
        {running ? (
          <>
            <Progress job={job} total={job.total || project.source_pages || 1} />
            <Button size="sm" onClick={() => api.post(`${P(id)}/cancel`)} title="Stop after the pages being read now">
              <Square size={12} /> Stop
            </Button>
          </>
        ) : (
          <>
            <StatusChip status={project.status} />
            <Button size="sm" variant={hasDoc ? "default" : "primary"} onClick={() => setShowConvert(true)} data-testid="convert-button">
              <Play size={13} /> {hasDoc ? "Read again…" : "Convert…"}
            </Button>
            <span className="flex-1" />
          </>
        )}
        {cost > 0 && (
          <span className="text-xs text-stone-500 dark:text-stone-400" title="What the Claude API has cost for this document so far" data-testid="cost">
            Claude cost: <b className="text-stone-700 dark:text-stone-200">{usd(cost)}</b>
          </span>
        )}
        <div className="flex items-center">
          <IconButton title="Show the detected blocks on the scan" active={showBoxes} onClick={() => setShowBoxes(!showBoxes)}>
            <Eye size={16} />
          </IconButton>
          <IconButton
            title={`Highlight words the reader was unsure of (${unsure})`}
            active={highlight}
            onClick={() => setHighlight(!highlight)}
            data-testid="toggle-unsure"
          >
            <Highlighter size={16} />
          </IconButton>
          {!narrow && (
            <IconButton title="Scroll the scan and the result together" active={sync} onClick={() => setSync(!sync)}>
              <Link2 size={16} />
            </IconButton>
          )}
          {!narrow && (
            <IconButton title="Style panel" active={styleOpen} onClick={() => setStyleOpen(!styleOpen)} data-testid="toggle-style">
              <Paintbrush size={16} />
            </IconButton>
          )}
        </div>
        <Menu
          button={({ toggle }) => (
            <Button size="sm" variant="primary" onClick={toggle} disabled={!done} data-testid="download-button">
              {exporting ? <Spinner size={13} /> : <Download size={14} />} Download
            </Button>
          )}
        >
          {(config?.formats || []).map((f) => (
            <MenuItem key={f.id} onClick={() => doExport(f.id)} hint={f.label} data-testid={`export-${f.id}`}>
              {f.id === "md" ? "Markdown" : f.id === "json" ? "ScanToDoc file" : f.id.toUpperCase()}{" "}
              <span className="text-xs text-stone-400">{f.ext}</span>
            </MenuItem>
          ))}
        </Menu>
      </div>

      {narrow ? (
        <>
          <div className="flex shrink-0 border-b border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900" role="tablist">
            {[
              ["scan", "Scan"],
              ["result", "Result"],
              ["style", "Style"],
            ].map(([k, l]) => (
              <button
                key={k}
                role="tab"
                aria-selected={tab === k}
                onClick={() => setTab(k)}
                className={cx(
                  "flex-1 border-b-2 py-2 text-sm font-medium",
                  tab === k ? "border-indigo-600 text-indigo-700 dark:text-indigo-300" : "border-transparent text-stone-500",
                )}
              >
                {l}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1">
            <div className={cx("h-full", tab !== "scan" && "hidden")}>{scan}</div>
            <div className={cx("h-full", tab !== "result" && "hidden")}>{result}</div>
            <div className={cx("pane h-full overflow-y-auto bg-white dark:bg-stone-900", tab !== "style" && "hidden")}>{stylePanel}</div>
          </div>
        </>
      ) : (
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1 border-r border-stone-200 dark:border-stone-800">{scan}</div>
          <div className="min-w-0 flex-1">{result}</div>
          {styleOpen && (
            <aside className="pane w-80 shrink-0 overflow-y-auto border-l border-stone-200 bg-white xl:w-88 dark:border-stone-800 dark:bg-stone-900" aria-label="Style">
              {stylePanel}
            </aside>
          )}
        </div>
      )}

      {showConvert && (
        <ConvertDialog
          project={{ ...project, document: doc }}
          config={config}
          openSettings={openSettings}
          onClose={() => setShowConvert(false)}
          onStart={() => {
            setShowConvert(false);
            setProject((p) => ({ ...p, status: "converting" }));
            follow();
          }}
        />
      )}
    </div>
  );
}
