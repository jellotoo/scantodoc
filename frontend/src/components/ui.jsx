import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";

const cx = (...c) => c.filter(Boolean).join(" ");
export { cx };

export function Button({ variant = "default", size = "md", className, children, ...props }) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500";
  const sizes = { sm: "h-7 px-2 text-xs", md: "h-9 px-3 text-sm", lg: "h-11 px-5 text-base" };
  const variants = {
    default:
      "border border-stone-300 bg-white text-stone-800 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:hover:bg-stone-800",
    primary: "bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm",
    ghost: "text-stone-600 hover:bg-stone-200/70 dark:text-stone-300 dark:hover:bg-stone-800",
    danger: "bg-red-600 text-white hover:bg-red-500",
  };
  return (
    <button className={cx(base, sizes[size], variants[variant], className)} {...props}>
      {children}
    </button>
  );
}

export function IconButton({ title, className, active, children, ...props }) {
  return (
    <button
      title={title}
      aria-label={title}
      aria-pressed={active === undefined ? undefined : !!active}
      className={cx(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40",
        active
          ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300"
          : "text-stone-600 hover:bg-stone-200/70 dark:text-stone-300 dark:hover:bg-stone-800",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx(
          "flex max-h-[92vh] w-full flex-col rounded-t-xl bg-white shadow-2xl sm:rounded-xl dark:bg-stone-900",
          wide ? "sm:max-w-2xl" : "sm:max-w-md",
        )}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3 dark:border-stone-800">
          <h2 className="text-base font-semibold">{title}</h2>
          <IconButton title="Close" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </div>
        <div className="overflow-y-auto px-4 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-stone-200 px-4 py-3 dark:border-stone-800">{footer}</div>}
      </div>
    </div>
  );
}

export function Toggle({ label, checked, onChange, hint, disabled }) {
  return (
    <label className={cx("flex cursor-pointer items-start gap-2.5 py-1", disabled && "cursor-not-allowed opacity-50")}>
      <button
        type="button"
        role="switch"
        aria-checked={!!checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-indigo-600" : "bg-stone-300 dark:bg-stone-700",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
      <span className="text-sm leading-snug">
        {label}
        {hint && <span className="block text-xs text-stone-500 dark:text-stone-400">{hint}</span>}
      </span>
    </label>
  );
}

export function Field({ label, hint, children, className }) {
  return (
    <label className={cx("block py-1", className)}>
      <span className="mb-1 block text-xs font-medium text-stone-600 dark:text-stone-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-stone-500 dark:text-stone-400">{hint}</span>}
    </label>
  );
}

export function Select({ value, onChange, options, className, ...props }) {
  return (
    <select className={cx("field", className)} value={value ?? ""} onChange={(e) => onChange(e.target.value)} {...props}>
      {options.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}

// A number box where "empty" means "keep what was detected" (null).
export function NumberInput({ value, onChange, placeholder = "Keep", step = 1, min, max, className, ...props }) {
  const [text, setText] = useState(value ?? "");
  useEffect(() => setText(value ?? ""), [value]);
  return (
    <input
      type="number"
      inputMode="decimal"
      className={cx("field", className)}
      value={text}
      step={step}
      min={min}
      max={max}
      placeholder={placeholder}
      onChange={(e) => {
        setText(e.target.value);
        if (e.target.value === "") onChange(null);
        else if (!Number.isNaN(Number(e.target.value))) onChange(Number(e.target.value));
      }}
      {...props}
    />
  );
}

// A colour picker with a "keep" state (null).
export function ColorInput({ value, onChange, label, keepLabel = "Keep" }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <input
        type="color"
        aria-label={label}
        value={value || "#000000"}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        className={cx("h-7 w-9 cursor-pointer rounded border border-stone-300 bg-transparent p-0.5 dark:border-stone-700", !value && "opacity-40")}
      />
      <span className="flex-1 text-sm">{label}</span>
      {value ? (
        <button className="text-xs text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => onChange(null)}>
          {keepLabel}
        </button>
      ) : (
        <span className="text-xs text-stone-400">{keepLabel.toLowerCase() === "keep" ? "as scanned" : "none"}</span>
      )}
    </div>
  );
}

export function Section({ title, icon: Icon, children, defaultOpen = false, badge }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-stone-200 dark:border-stone-800">
      <button
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-semibold hover:bg-stone-100 dark:hover:bg-stone-800/60"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {Icon && <Icon size={16} className="text-stone-500" />}
        <span className="flex-1">{title}</span>
        {badge && <span className="rounded bg-indigo-100 px-1.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300">{badge}</span>}
        <ChevronDown size={16} className={cx("text-stone-400 transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

export function Segmented({ value, onChange, options, className }) {
  return (
    <div className={cx("inline-flex w-full rounded-md border border-stone-300 p-0.5 dark:border-stone-700", className)} role="radiogroup">
      {options.map(([v, l]) => (
        <button
          key={v}
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cx(
            "flex-1 rounded px-2 py-1 text-xs font-medium transition-colors",
            value === v ? "bg-indigo-600 text-white" : "text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800",
          )}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

export function Menu({ button, children, align = "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => !ref.current?.contains(e.target) && setOpen(false);
    const key = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      {button({ open, toggle: () => setOpen(!open) })}
      {open && (
        <div
          className={cx(
            "absolute z-40 mt-1 min-w-56 overflow-hidden rounded-lg border border-stone-200 bg-white py-1 shadow-xl dark:border-stone-700 dark:bg-stone-900",
            align === "right" ? "right-0" : "left-0",
          )}
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function MenuItem({ icon: Icon, children, hint, ...props }) {
  return (
    <button className="flex w-full items-start gap-2.5 px-3 py-2 text-left text-sm hover:bg-stone-100 disabled:opacity-50 dark:hover:bg-stone-800" {...props}>
      {Icon && <Icon size={16} className="mt-0.5 shrink-0 text-stone-500" />}
      <span>
        {children}
        {hint && <span className="block text-xs text-stone-500 dark:text-stone-400">{hint}</span>}
      </span>
    </button>
  );
}

export function Spinner({ size = 16, className }) {
  return (
    <svg className={cx("animate-spin", className)} width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------- toasts

const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message, opts = {}) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, kind: opts.kind || "info", action: opts.action }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), opts.duration || (opts.kind === "error" ? 8000 : 4000));
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-3 z-[60] flex flex-col items-center gap-2 px-3" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={cx(
              "pointer-events-auto flex max-w-lg items-center gap-3 rounded-lg px-4 py-2.5 text-sm shadow-lg",
              t.kind === "error" ? "bg-red-600 text-white" : "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900",
            )}
          >
            <span className="flex-1">{t.message}</span>
            {t.action && (
              <button
                className="font-semibold underline"
                onClick={() => {
                  t.action.run();
                  setToasts((all) => all.filter((x) => x.id !== t.id));
                }}
              >
                {t.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
