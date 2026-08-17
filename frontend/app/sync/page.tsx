"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, FileDiff, FolderSync, Menu, Play, RefreshCw, RotateCcw, Save, ServerCrash } from "lucide-react";
import { NavigationDock } from "../components/NavigationDock";
import { SyncFilter, SyncSidebar } from "../components/SyncSidebar";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SyncConfig {
  enabled: boolean;
  destination_subpath: string;
  mounted: boolean;
  writable: boolean;
  root_label: string;
}

interface CourseSyncState {
  course_name: string;
  available: boolean;
  enabled: boolean;
  filename: string;
  status: "disabled" | "syncing" | "synced" | "conflict" | "missing" | "error";
  last_synced_at: string | null;
  external_changed_at: string | null;
  last_error: string | null;
  has_conflict: boolean;
}

interface DirectoryItem { name: string; path: string }
interface ConflictDetails { course_name: string; status: string; file_exists: boolean; diff: string; external_size: number; database_size: number }

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "La operación no pudo completarse.");
  }
  return response.json() as Promise<T>;
}

export default function SyncPage() {
  const [config, setConfig] = useState<SyncConfig | null>(null);
  const [courses, setCourses] = useState<CourseSyncState[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [filter, setFilter] = useState<SyncFilter>("all");
  const [directories, setDirectories] = useState<DirectoryItem[]>([]);
  const [currentDirectory, setCurrentDirectory] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<ConflictDetails | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextConfig, nextCourses] = await Promise.all([
        apiRequest<SyncConfig>("/api/local-sync/config"),
        apiRequest<CourseSyncState[]>("/api/local-sync/courses"),
      ]);
      setConfig(nextConfig);
      setCourses(nextCourses);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo consultar el estado.");
    }
  }, []);

  const browse = useCallback(async (path: string) => {
    try {
      const data = await apiRequest<{ path: string; directories: DirectoryItem[] }>(`/api/local-sync/directories?path=${encodeURIComponent(path)}`);
      setCurrentDirectory(path);
      setDirectories(data.directories);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo abrir la carpeta.");
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); void browse(""); }, 0);
    return () => window.clearTimeout(initial);
  }, [refresh, browse]);
  useEffect(() => { const timer = window.setInterval(() => void refresh(), 3000); return () => window.clearInterval(timer); }, [refresh]);

  const visibleCourses = useMemo(() => courses.filter((course) => {
    if (filter === "active") return course.enabled;
    if (filter === "conflicts") return course.has_conflict;
    return true;
  }), [courses, filter]);

  const updateConfig = async (payload: Partial<Pick<SyncConfig, "enabled" | "destination_subpath">>) => {
    setBusy("config");
    try {
      const next = await apiRequest<SyncConfig>("/api/local-sync/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setConfig(next); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo guardar la configuración."); }
    finally { setBusy(null); }
  };

  const toggleCourse = async (course: CourseSyncState) => {
    setBusy(course.course_name);
    try {
      await apiRequest(`/api/local-sync/courses/${encodeURIComponent(course.course_name)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !course.enabled }) });
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cambiar el curso."); }
    finally { setBusy(null); }
  };

  const runSync = async () => {
    setBusy("run");
    try { await apiRequest("/api/local-sync/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo sincronizar."); }
    finally { setBusy(null); }
  };

  const inspectConflict = async (courseName: string) => {
    setBusy(courseName);
    try { setConflict(await apiRequest(`/api/local-sync/courses/${encodeURIComponent(courseName)}/conflict`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo generar el diff."); }
    finally { setBusy(null); }
  };

  const resolveConflict = async (action: "integrate_external" | "restore_database") => {
    if (!conflict) return;
    setBusy(conflict.course_name);
    try {
      await apiRequest(`/api/local-sync/courses/${encodeURIComponent(conflict.course_name)}/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) });
      setConflict(null); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo resolver el conflicto."); }
    finally { setBusy(null); }
  };

  if (!config) {
    return <div className="min-h-screen bg-slate-950 text-slate-200 flex items-center justify-center"><RefreshCw className="h-8 w-8 animate-spin text-cyan-400" /></div>;
  }

  const conflictCount = courses.filter((course) => course.has_conflict).length;
  return (
    <div className="min-h-screen overflow-hidden bg-slate-950 px-4 pb-28 pt-8 font-sans text-slate-100 md:px-8">
      <div className="pointer-events-none fixed left-[-10%] top-[-10%] h-[50%] w-[50%] rounded-full bg-cyan-900/10 blur-[120px]" />
      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col">
        <header className="mb-8 flex flex-col justify-between gap-4 border-b border-slate-800 pb-6 md:flex-row md:items-center">
          <div className="flex items-center gap-3.5">
            <button onClick={() => setSidebarOpen(true)} className="relative rounded-xl border border-slate-800 bg-slate-900 p-3 text-cyan-400 hover:bg-slate-800" aria-label="Abrir herramientas">
              <Menu className="h-6 w-6" />
              {conflictCount > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-amber-500 text-[10px] font-bold text-slate-950">{conflictCount}</span>}
            </button>
            <div className="rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 p-3 shadow-lg shadow-cyan-500/20"><FolderSync className="h-7 w-7" /></div>
            <div><h1 className="text-2xl font-extrabold tracking-tight md:text-3xl">Sincronización local</h1><p className="mt-1 text-sm text-slate-400">Mantén copias Markdown completas y revisa los cambios externos antes de integrarlos.</p></div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => void runSync()} disabled={busy !== null || !config.enabled} className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2.5 text-xs font-bold text-slate-200 disabled:opacity-40"><Play className="h-4 w-4" /> Sincronizar ahora</button>
            <button onClick={() => void updateConfig({ enabled: !config.enabled })} disabled={!config.mounted || !config.writable} className={`rounded-xl px-4 py-2.5 text-xs font-bold ${config.enabled ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30" : "bg-slate-800 text-slate-300 border border-slate-700"}`}>{config.enabled ? "Sistema activo" : "Activar sistema"}</button>
          </div>
        </header>

        {error && <div className="mb-5 flex items-center justify-between rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span className="flex items-center gap-2"><ServerCrash className="h-4 w-4" />{error}</span><button onClick={() => setError("")}>×</button></div>}

        <section className="mb-6 grid gap-4 md:grid-cols-3">
          <StatusCard label="Carpeta" value={config.mounted && config.writable ? "Preparada" : "No disponible"} detail={config.destination_subpath} tone={config.mounted && config.writable ? "good" : "bad"} />
          <StatusCard label="Cursos activos" value={`${courses.filter((course) => course.enabled).length}`} detail={`${courses.length} cursos procesados`} tone="info" />
          <StatusCard label="Conflictos" value={`${conflictCount}`} detail={conflictCount ? "Requieren revisión" : "Todo está al día"} tone={conflictCount ? "warn" : "good"} />
        </section>

        <main className="rounded-2xl border border-slate-800 bg-slate-900/50 shadow-xl backdrop-blur">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4"><div><h2 className="font-bold">Cursos</h2><p className="text-xs text-slate-500">Un archivo concatenado por cada curso seleccionado.</p></div><span className="text-xs text-slate-500">Filtro: {filter === "all" ? "todos" : filter === "active" ? "activos" : "conflictos"}</span></div>
          <div className="divide-y divide-slate-800">
            {visibleCourses.map((course) => (
              <article key={course.course_name} className="flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center">
                <button role="switch" aria-checked={course.enabled} onClick={() => void toggleCourse(course)} disabled={busy === course.course_name || !config.enabled || !course.available} className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40 ${course.enabled ? "bg-cyan-500" : "bg-slate-700"}`}><span className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform ${course.enabled ? "translate-x-5" : "translate-x-0"}`} /></button>
                <div className="min-w-0 flex-1"><h3 className="truncate text-sm font-bold text-slate-200">{course.course_name}</h3><p className="mt-1 truncate font-mono text-[10px] text-slate-500">{course.filename}</p></div>
                <SyncBadge status={course.status} />
                <div className="w-44 text-right text-[11px] text-slate-500">{course.last_synced_at ? `Última copia: ${new Date(course.last_synced_at).toLocaleString()}` : "Todavía no sincronizado"}</div>
                {course.has_conflict && <button onClick={() => void inspectConflict(course.course_name)} className="flex items-center justify-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs font-bold text-amber-300"><FileDiff className="h-4 w-4" /> Revisar</button>}
              </article>
            ))}
            {visibleCourses.length === 0 && <div className="px-5 py-16 text-center text-sm text-slate-500">No hay cursos para este filtro.</div>}
          </div>
        </main>
      </div>

      <SyncSidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} filter={filter} onFilterChange={setFilter} destination={config.destination_subpath} mounted={config.mounted} writable={config.writable} directories={directories} currentDirectory={currentDirectory} onBrowse={(path) => void browse(path)} onChoose={(path) => { void updateConfig({ destination_subpath: path === "." ? "Cursos" : path }); setSidebarOpen(false); }} onCreateDirectory={async (name) => { await apiRequest("/api/local-sync/directories", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parent: currentDirectory, name }) }); await browse(currentDirectory); }} />
      <NavigationDock />

      {conflict && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4"><div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"><div className="flex items-center justify-between border-b border-slate-800 p-5"><div><h2 className="font-bold">Cambios externos — {conflict.course_name}</h2><p className="mt-1 text-xs text-slate-500">El archivo local permanece intacto hasta que elijas una acción.</p></div><button onClick={() => setConflict(null)} className="text-slate-400 hover:text-white">×</button></div><pre className="flex-1 overflow-auto bg-slate-950 p-5 font-mono text-[11px] leading-relaxed text-slate-300">{conflict.diff || "El archivo no existe en el destino."}</pre><div className="flex flex-col-reverse justify-end gap-3 border-t border-slate-800 p-4 sm:flex-row"><button onClick={() => void resolveConflict("restore_database")} className="flex items-center justify-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-xs font-bold"><RotateCcw className="h-4 w-4" /> Restaurar desde la app</button>{conflict.file_exists && <button onClick={() => void resolveConflict("integrate_external")} className="flex items-center justify-center gap-2 rounded-xl bg-cyan-600 px-4 py-2.5 text-xs font-bold text-white"><Save className="h-4 w-4" /> Integrar cambios externos</button>}</div></div></div>}
    </div>
  );
}

function StatusCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: "good" | "bad" | "warn" | "info" }) {
  const colors = { good: "text-emerald-300 border-emerald-500/20", bad: "text-rose-300 border-rose-500/20", warn: "text-amber-300 border-amber-500/20", info: "text-cyan-300 border-cyan-500/20" };
  return <div className={`rounded-2xl border bg-slate-900/60 p-4 ${colors[tone]}`}><p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{label}</p><p className="mt-2 text-2xl font-black">{value}</p><p className="mt-1 truncate text-xs text-slate-500">{detail}</p></div>;
}

function SyncBadge({ status }: { status: CourseSyncState["status"] }) {
  const values = { disabled: ["Desactivado", "text-slate-400 bg-slate-800"], syncing: ["Sincronizando", "text-cyan-300 bg-cyan-500/10"], synced: ["Sincronizado", "text-emerald-300 bg-emerald-500/10"], conflict: ["Conflicto", "text-amber-300 bg-amber-500/10"], missing: ["Archivo ausente", "text-amber-300 bg-amber-500/10"], error: ["Error", "text-rose-300 bg-rose-500/10"] } as const;
  const [label, classes] = values[status];
  return <span className={`inline-flex w-32 items-center justify-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold ${classes}`}>{status === "synced" ? <Check className="h-3 w-3" /> : status === "conflict" || status === "missing" ? <AlertTriangle className="h-3 w-3" /> : null}{label}</span>;
}
