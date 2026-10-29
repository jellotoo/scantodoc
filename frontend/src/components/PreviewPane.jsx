import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef } from "react";
import { runsToHtml, htmlToRuns } from "../runs.js";

// The result is rendered by the server's own HTML exporter, so what you see
// here is what the exports contain. It lives in a shadow root, so the app's
// CSS and the document's CSS never mix.

const BASE_CSS = `
:host { all: initial; display: block; }
.wrap { padding: 16px 12px 40px; zoom: var(--z, 1); }
.sheet { position: relative; margin: 0 auto 20px; box-sizing: border-box; box-shadow: 0 1px 4px rgba(0,0,0,.18); color: #111; }
.pg { position: absolute; top: 6px; inset-inline-end: 10px; font: 11px system-ui, sans-serif; color: #a8a29e; user-select: none; }
.empty { font: 13px system-ui, sans-serif; color: #a8a29e; text-align: center; padding: 40px 0; }
[data-id] { cursor: pointer; border-radius: 2px; transition: background-color .12s, box-shadow .12s; }
[data-id]:hover, [data-id].hov { background-color: rgba(99,102,241,.07); }
[data-id].sel { box-shadow: 0 0 0 2px #6366f1; background-color: rgba(99,102,241,.06); }
[data-id].editing { box-shadow: 0 0 0 2px #10b981; background-color: #fff; cursor: text; outline: none; }
[data-dropped] { opacity: .38; }
[data-dropped]::after { content: "  (left out of exports)"; font: italic 10px system-ui, sans-serif; color: #78716c; }
.hl .unc { background: #fde68a; border-radius: 2px; }
.editing .unc { background: #fde68a; }
img { max-width: 100%; }
`;

const PreviewPane = forwardRef(function PreviewPane(
  { preview, doc, selected, hovered, editingId, highlightUnsure, onSelect, onHover, onStartEdit, onSaveEdit, onCancelEdit, onScroll },
  ref,
) {
  const scrollRef = useRef(null);
  const hostRef = useRef(null);
  const rootRef = useRef(null);
  const cb = useRef({});
  cb.current = { onSelect, onHover, onStartEdit, onSaveEdit, onCancelEdit, editingId, doc };
  const editState = useRef(null); // { id, el, original }

  useImperativeHandle(ref, () => ({
    get el() {
      return scrollRef.current;
    },
    sections() {
      return [...(rootRef.current?.querySelectorAll("section[data-page]") || [])];
    },
    blockEl(id) {
      return rootRef.current?.querySelector(`[data-id="${CSS.escape(id)}"]`);
    },
    format(cmd) {
      document.execCommand(cmd);
    },
    save() {
      finishEdit(true);
    },
    cancel() {
      finishEdit(false);
    },
  }));

  // Create the shadow root and its event handlers once.
  useLayoutEffect(() => {
    const host = hostRef.current;
    const root = host.shadowRoot || host.attachShadow({ mode: "open" });
    rootRef.current = root;
    const target = (e) => e.target.closest?.("[data-id]");
    const click = (e) => {
      const el = target(e);
      if (editState.current && el === editState.current.el) return;
      if (e.target.closest("a")) e.preventDefault();
      cb.current.onSelect(el ? el.dataset.id : null, "preview");
    };
    const dbl = (e) => {
      const el = target(e);
      if (el && !editState.current) cb.current.onStartEdit(el.dataset.id);
    };
    const over = (e) => {
      const el = target(e);
      cb.current.onHover(el ? el.dataset.id : null);
    };
    const key = (e) => {
      if (!editState.current) return;
      if (e.key === "Escape") {
        e.preventDefault();
        finishEdit(false);
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        finishEdit(true);
      }
    };
    root.addEventListener("click", click);
    root.addEventListener("dblclick", dbl);
    root.addEventListener("mouseover", over);
    root.addEventListener("keydown", key);
    return () => {
      root.removeEventListener("click", click);
      root.removeEventListener("dblclick", dbl);
      root.removeEventListener("mouseover", over);
      root.removeEventListener("keydown", key);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function finishEdit(save) {
    const st = editState.current;
    if (!st) return;
    editState.current = null;
    st.el.removeEventListener("focusout", st.onBlur);
    st.el.contentEditable = "false";
    st.el.classList.remove("editing");
    if (save) {
      const runs = htmlToRuns(st.el);
      cb.current.onSaveEdit(st.id, runs, st.original);
    } else {
      st.el.innerHTML = st.html;
      cb.current.onCancelEdit();
    }
  }

  // Bundled web fonts must be declared in the main document to work inside a shadow root.
  useEffect(() => {
    let tag = document.getElementById("scantodoc-preview-fonts");
    if (!tag) {
      tag = document.createElement("style");
      tag.id = "scantodoc-preview-fonts";
      document.head.appendChild(tag);
    }
    if (preview?.fonts !== undefined && tag.textContent !== preview.fonts) tag.textContent = preview.fonts;
  }, [preview?.fonts]);

  // Render the document (not while a block is being edited).
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || editState.current) return;
    const pages = doc?.pages || [];
    if (!preview || preview.empty) {
      root.innerHTML = `<style>${BASE_CSS}</style><div class="wrap"><p class="empty">${pages.length ? "Preparing the preview…" : "The converted document will appear here."}</p></div>`;
      return;
    }
    const [mt, mr, mb, ml] = preview.margins;
    const sheet = `width:${preview.page_w}in;min-height:${preview.page_h}in;padding:${mt}in ${mr}in ${mb}in ${ml}in;background:${preview.background}`;
    const dir = preview.direction;
    let html = `<style>${BASE_CSS}\n${preview.css}</style><div class="wrap${highlightUnsure ? " hl" : ""}">`;
    if (preview.front) html += `<section class="sheet" data-front="1" style="${sheet}"><div class="doc" dir="${dir}">${preview.front}</div></section>`;
    for (const p of pages) {
      const body = preview.pages[String(p.index)];
      const placeholder =
        p.status === "error"
          ? `<p class="empty">This page could not be read: ${p.error ? p.error.replace(/</g, "&lt;") : "unknown error"}</p>`
          : `<p class="empty">${p.status === "done" ? "(no text on this page)" : "Not read yet…"}</p>`;
      html += `<section class="sheet" data-page="${p.index}" style="${sheet}"><span class="pg">${p.index + 1}</span><div class="doc" dir="${dir}">${body || placeholder}</div></section>`;
    }
    html += "</div>";
    root.innerHTML = html;
    markClasses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview, doc]);

  function markClasses() {
    const root = rootRef.current;
    if (!root) return;
    root.querySelectorAll(".sel,.hov").forEach((el) => el.classList.remove("sel", "hov"));
    if (selected) root.querySelector(`[data-id="${CSS.escape(selected)}"]`)?.classList.add("sel");
    if (hovered && hovered !== selected) root.querySelector(`[data-id="${CSS.escape(hovered)}"]`)?.classList.add("hov");
    root.querySelector(".wrap")?.classList.toggle("hl", !!highlightUnsure);
  }
  useEffect(markClasses, [selected, hovered, highlightUnsure]); // eslint-disable-line react-hooks/exhaustive-deps

  // Start editing a block: show its raw text and formatting, editable in place.
  useEffect(() => {
    if (!editingId || editState.current?.id === editingId) return;
    const el = rootRef.current?.querySelector(`[data-id="${CSS.escape(editingId)}"]`);
    let block = null;
    for (const p of doc?.pages || []) for (const b of p.blocks) if (b.id === editingId) block = b;
    if (!el || !block) return;
    const marker = el.querySelector(".mk");
    const st = { id: editingId, el, original: block.runs, html: el.innerHTML };
    el.innerHTML = (marker ? marker.outerHTML : "") + runsToHtml(block.runs);
    el.contentEditable = "true";
    el.classList.add("editing");
    el.spellcheck = true;
    st.onBlur = (e) => {
      // Clicks on the editing toolbar keep focus (they use preventDefault on mousedown).
      if (!el.contains(e.relatedTarget)) setTimeout(() => editState.current === st && finishEdit(true), 0);
    };
    el.addEventListener("focusout", st.onBlur);
    editState.current = st;
    el.focus();
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingId]);

  // Fit the page width to the pane.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !preview?.page_w) return;
    const fit = () => {
      const z = Math.min(1.3, Math.max(0.3, (el.clientWidth - 28) / (preview.page_w * 96)));
      hostRef.current.style.setProperty("--z", z.toFixed(3));
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [preview?.page_w]);

  return (
    <div ref={scrollRef} onScroll={onScroll} className="pane h-full overflow-y-auto bg-stone-200/70 dark:bg-stone-900/60" data-testid="preview-pane">
      <div ref={hostRef} data-testid="preview-host" />
    </div>
  );
});

export default PreviewPane;
