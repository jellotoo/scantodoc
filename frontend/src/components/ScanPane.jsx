import { forwardRef, useState } from "react";
import { RefreshCw, Sparkles, Cpu, AlertTriangle } from "lucide-react";
import { pageImage, usd } from "../api.js";
import { TYPE_COLORS } from "../styleutil.js";
import { Menu, MenuItem, Spinner, cx } from "./ui.jsx";

const READER_LABEL = { local: "Local OCR", claude: "Claude", textlayer: "PDF text", import: "Imported" };

function PageBadge({ page }) {
  if (page.status === "error")
    return (
      <span className="flex items-center gap-1 text-red-600 dark:text-red-400" title={page.error}>
        <AlertTriangle size={12} /> Failed
      </span>
    );
  if (page.status !== "done") return <span className="text-stone-400">{page.status === "reading" ? "Reading…" : "Not read yet"}</span>;
  return (
    <span className="text-stone-500 dark:text-stone-400" title={page.error || undefined}>
      {READER_LABEL[page.reader] || page.reader}
      {page.quality != null && ` · ${Math.round(page.quality)}% sure`}
      {page.usage?.cost_usd > 0 && ` · ${usd(page.usage.cost_usd)}`}
    </span>
  );
}

const ScanPane = forwardRef(function ScanPane(
  { projectId, doc, selected, hovered, onSelect, onHover, showBoxes, onScroll, onReread, rereading, hasKey, live },
  ref,
) {
  const [loaded, setLoaded] = useState({});
  const pages = doc?.pages || [];
  return (
    <div ref={ref} onScroll={onScroll} className="pane h-full overflow-y-auto bg-stone-200/70 px-3 py-4 dark:bg-stone-900/60" data-testid="scan-pane">
      {pages.length === 0 && (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-stone-500">
          {live ? <Spinner /> : null}
          {live ? "Preparing page images…" : "No pages yet."}
        </div>
      )}
      <div className="mx-auto flex max-w-[900px] flex-col gap-5">
        {pages.map((page) => (
          <section key={page.index} data-page={page.index} className="scroll-mt-2">
            <div className="mb-1.5 flex items-center gap-2 text-xs">
              <span className="font-semibold text-stone-700 dark:text-stone-300">Page {page.index + 1}</span>
              <PageBadge page={page} />
              <span className="flex-1" />
              {rereading === page.index ? (
                <Spinner size={14} className="text-indigo-600" />
              ) : (
                page.image && (
                  <Menu
                    button={({ toggle }) => (
                      <button
                        onClick={toggle}
                        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-stone-500 hover:bg-stone-300/60 hover:text-stone-800 dark:hover:bg-stone-700 dark:hover:text-stone-100"
                        title="Read this page again"
                        disabled={live}
                      >
                        <RefreshCw size={12} /> Re-read
                      </button>
                    )}
                  >
                    <MenuItem icon={Sparkles} disabled={!hasKey} onClick={() => onReread(page.index, "claude")} hint={hasKey ? "Best for hard pages; costs about $0.002–0.05" : "Add an API key in Settings first"}>
                      Re-read with Claude
                    </MenuItem>
                    <MenuItem icon={Cpu} onClick={() => onReread(page.index, "local")} hint="Free; replaces your corrections on this page">
                      Re-read locally
                    </MenuItem>
                  </Menu>
                )
              )}
            </div>
            <div
              className="relative overflow-hidden rounded bg-white shadow-sm ring-1 ring-stone-300 dark:ring-stone-700"
              style={{ aspectRatio: page.width_px && page.height_px ? `${page.width_px} / ${page.height_px}` : "8.5 / 11" }}
              onMouseLeave={() => onHover(null)}
            >
              {page.image && (
                <img
                  src={pageImage(projectId, page.image, 1400)}
                  alt={`Scanned page ${page.index + 1}`}
                  className={cx("absolute inset-0 h-full w-full transition-opacity", loaded[page.index] ? "opacity-100" : "opacity-0")}
                  onLoad={() => setLoaded((l) => ({ ...l, [page.index]: true }))}
                  loading="lazy"
                  draggable={false}
                />
              )}
              {page.status === "reading" && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/40 dark:bg-black/30">
                  <span className="flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-medium text-stone-700 shadow">
                    <Spinner size={14} className="text-indigo-600" /> Reading…
                  </span>
                </div>
              )}
              {showBoxes &&
                page.blocks.map((b) => {
                  if (!b.bbox) return null;
                  const [x0, y0, x1, y1] = b.bbox;
                  const color = TYPE_COLORS[b.type] || "#6366f1";
                  const sel = selected === b.id;
                  const hov = hovered === b.id;
                  return (
                    <button
                      key={b.id}
                      data-box={b.id}
                      title={`${b.type === "heading" ? `Heading ${b.level}` : b.type.replace("_", " ")} — click to select`}
                      aria-label={`Select ${b.type} block`}
                      onClick={() => onSelect(b.id, "scan")}
                      onMouseEnter={() => onHover(b.id)}
                      className="absolute rounded-[2px] transition-[background-color,box-shadow]"
                      style={{
                        left: `${x0 * 100}%`,
                        top: `${y0 * 100}%`,
                        width: `${(x1 - x0) * 100}%`,
                        height: `${(y1 - y0) * 100}%`,
                        boxShadow: `0 0 0 ${sel ? 2.5 : 1}px ${color}${sel || hov ? "" : "99"}`,
                        backgroundColor: sel ? `${color}2e` : hov ? `${color}1a` : "transparent",
                      }}
                    />
                  );
                })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
});

export default ScanPane;
