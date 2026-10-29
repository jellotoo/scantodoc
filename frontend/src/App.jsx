import { useCallback, useEffect, useState } from "react";
import { FileText, Monitor, Moon, Settings as SettingsIcon, Sun } from "lucide-react";
import { api } from "./api.js";
import { IconButton, ToastProvider } from "./components/ui.jsx";
import ProjectsList from "./components/ProjectsList.jsx";
import Workspace from "./components/Workspace.jsx";
import Settings from "./components/Settings.jsx";

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const m = hash.match(/^#\/p\/([^/?]+)(\?new)?/);
  return m ? { page: "project", id: decodeURIComponent(m[1]), isNew: !!m[2] } : { page: "projects" };
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("scantodoc-theme") || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.classList.toggle("dark", theme === "dark" || (theme === "system" && mq.matches));
    apply();
    try {
      localStorage.setItem("scantodoc-theme", theme);
    } catch {
      /* private window */
    }
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  return [theme, setTheme];
}

export default function App() {
  const route = useHashRoute();
  const [config, setConfig] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [theme, setTheme] = useTheme();
  const [title, setTitle] = useState(null);

  const loadConfig = useCallback(() => api.get("/api/config").then(setConfig).catch(() => {}), []);
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const nextTheme = { system: "light", light: "dark", dark: "system" }[theme];
  const ThemeIcon = { system: Monitor, light: Sun, dark: Moon }[theme];

  return (
    <ToastProvider>
      <div className="flex h-full flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-stone-200 bg-white px-3 dark:border-stone-800 dark:bg-stone-900">
          <a href="#/" className="flex items-center gap-2 font-semibold tracking-tight" title="All projects">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-white">
              <FileText size={16} />
            </span>
            <span className="hidden sm:inline">ScanToDoc</span>
          </a>
          {route.page === "project" && title && (
            <>
              <span className="text-stone-300 dark:text-stone-600">/</span>
              <span className="truncate text-sm text-stone-600 dark:text-stone-300">{title}</span>
            </>
          )}
          <div className="flex-1" />
          <IconButton title={`Theme: ${theme} (click for ${nextTheme})`} onClick={() => setTheme(nextTheme)}>
            <ThemeIcon size={17} />
          </IconButton>
          <IconButton title="Settings" onClick={() => setShowSettings(true)}>
            <SettingsIcon size={17} />
          </IconButton>
        </header>
        <main className="min-h-0 flex-1">
          {route.page === "projects" ? (
            <ProjectsList config={config} />
          ) : (
            <Workspace
              key={route.id}
              id={route.id}
              isNew={route.isNew}
              config={config}
              onTitle={setTitle}
              openSettings={() => setShowSettings(true)}
            />
          )}
        </main>
        {showSettings && (
          <Settings
            config={config}
            theme={theme}
            setTheme={setTheme}
            onChanged={loadConfig}
            onClose={() => setShowSettings(false)}
          />
        )}
      </div>
    </ToastProvider>
  );
}
