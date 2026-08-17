"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, Download, Edit3, Eye, EyeOff, Layers3, Menu, Play, RefreshCw, Search, ToggleLeft, ToggleRight } from "lucide-react";
import { FlashcardsSidebar } from "../components/FlashcardsSidebar";
import { NavigationDock } from "../components/NavigationDock";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ClassNode { class_title: string; count: number }
interface ModuleNode { module_name: string; count: number; classes: ClassNode[] }
interface CourseNode { course_name: string; count: number; modules: ModuleNode[] }
interface Summary { total: number; new: number; learning: number; review: number; due: number; inactive: number }
interface Card {
  id: string; course_name: string; course_module: string; class_title: string; deck_tag: string;
  question: string; answer: string; is_active: boolean; learning_state: "new" | "learning" | "review";
  due_at: string | null; interval_days: number; review_count: number;
  maturity: "new" | "learning" | "young" | "mature";
  review_options: Array<{ rating: number; label: string; meaning: string; due_label: string }>;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "No se pudo completar la operación.");
  }
  return response.json() as Promise<T>;
}

export default function FlashcardsPage() {
  const [tree, setTree] = useState<CourseNode[]>([]);
  const [summary, setSummary] = useState<Summary>({ total: 0, new: 0, learning: 0, review: 0, due: 0, inactive: 0 });
  const [cards, setCards] = useState<Card[]>([]);
  const [course, setCourse] = useState("");
  const [module, setModule] = useState("");
  const [classTitle, setClassTitle] = useState("");
  const [search, setSearch] = useState("");
  const [visibleStates, setVisibleStates] = useState({ active: true, inactive: false });
  const [stateMenuOpen, setStateMenuOpen] = useState(false);
  const [mode, setMode] = useState<"library" | "study">("library");
  const [revealed, setRevealed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [editing, setEditing] = useState<Card | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: mode === "study" ? "200" : "200" });
    if (course) params.set("course", course);
    if (module) params.set("module", module);
    if (classTitle) params.set("class_title", classTitle);
    if (search && mode === "library") params.set("search", search);
    if (mode === "library") {
      params.set("activity", visibleStates.active && visibleStates.inactive ? "all" : visibleStates.inactive ? "inactive" : "active");
    }
    if (mode === "study") params.set("due_only", "true");
    return params.toString();
  }, [course, module, classTitle, search, visibleStates, mode]);

  const selectedCourse = tree.find((item) => item.course_name === course);
  const selectedModule = selectedCourse?.modules.find((item) => item.module_name === module);
  const toggleVisibleState = (key: "active" | "inactive") => {
    setVisibleStates((current) => {
      if (current[key] && Object.values(current).filter(Boolean).length === 1) return current;
      return { ...current, [key]: !current[key] };
    });
  };

  const refresh = useCallback(async () => {
    try {
      const filter = new URLSearchParams();
      if (course) filter.set("course", course);
      if (module) filter.set("module", module);
      if (classTitle) filter.set("class_title", classTitle);
      const [nextTree, nextSummary, result] = await Promise.all([
        api<CourseNode[]>("/api/flashcards/tree"),
        api<Summary>(`/api/flashcards/summary?${filter}`),
        api<{ total: number; items: Card[] }>(`/api/flashcards?${query}`),
      ]);
      setTree(nextTree); setSummary(nextSummary); setCards(result.items); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cargar la biblioteca."); }
  }, [course, module, classTitle, query]);

  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timer); }, [refresh]);

  const current = cards[0];
  const review = async (rating: number) => {
    if (!current) return;
    setBusy(true);
    try {
      await api(`/api/flashcards/${current.id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rating }) });
      setCards((items) => items.slice(1)); setRevealed(false);
      const params = new URLSearchParams(); if (course) params.set("course", course); if (module) params.set("module", module); if (classTitle) params.set("class_title", classTitle);
      setSummary(await api(`/api/flashcards/summary?${params}`));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo guardar el repaso."); }
    finally { setBusy(false); }
  };

  const download = async (format: "csv" | "anki") => {
    setBusy(true);
    try {
      const params = new URLSearchParams(); if (course) params.set("course", course); if (module) params.set("module", module); if (classTitle) params.set("class_title", classTitle);
      const response = await fetch(`${API_BASE}/api/flashcards/export/${format}?${params}`);
      if (!response.ok) throw new Error("No se pudo generar la exportación.");
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `flashcards.${format === "anki" ? "apkg" : "csv"}`;
      const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo exportar."); }
    finally { setBusy(false); }
  };

  const reindex = async () => {
    setBusy(true);
    try { await api("/api/flashcards/reindex", { method: "POST" }); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo reindexar."); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-slate-950 px-4 pb-28 pt-8 text-slate-100 md:px-8">
      <div className="pointer-events-none fixed right-[-10%] top-[-15%] h-[55%] w-[55%] rounded-full bg-violet-900/10 blur-[130px]" />
      <div className="relative z-10 mx-auto max-w-7xl">
        <header className="mb-7 flex flex-col justify-between gap-4 border-b border-slate-800 pb-6 lg:flex-row lg:items-center">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="rounded-xl border border-slate-800 bg-slate-900 p-3 text-violet-400"><Menu className="h-6 w-6" /></button>
            <div className="rounded-xl bg-gradient-to-tr from-violet-600 to-fuchsia-600 p-3 shadow-lg shadow-violet-500/20"><Layers3 className="h-7 w-7" /></div>
            <div><h1 className="text-2xl font-extrabold md:text-3xl">Flashcards</h1><p className="mt-1 text-sm text-slate-400">Biblioteca indexada, repasos programados y exportaciones portables.</p></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => void reindex()} disabled={busy} className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-bold"><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Reindexar</button>
            <button onClick={() => void download("csv")} disabled={busy} className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-bold"><Download className="h-4 w-4" /> CSV</button>
            <button onClick={() => void download("anki")} disabled={busy} className="flex items-center gap-2 rounded-xl bg-violet-600 px-3 py-2 text-xs font-bold"><Download className="h-4 w-4" /> Anki</button>
          </div>
        </header>

        {error && <div className="mb-5 flex justify-between rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}

        <section className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Total" value={summary.total} tone="text-violet-300" /><Stat label="Pendientes" value={summary.due} tone="text-amber-300" /><Stat label="Nuevas" value={summary.new} tone="text-cyan-300" /><Stat label="Aprendiendo" value={summary.learning} tone="text-fuchsia-300" /><Stat label="Repaso" value={summary.review} tone="text-emerald-300" />
        </section>

        <div className="mb-5 flex flex-col gap-3">
          <div className="grid gap-3 md:grid-cols-3">
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Curso
              <select value={course} onChange={(event) => { setCourse(event.target.value); setModule(""); setClassTitle(""); setRevealed(false); }} className="mt-1.5 w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2.5 text-sm font-normal normal-case text-slate-200 outline-none">
                <option value="">Todos los cursos</option>{tree.map((item) => <option key={item.course_name} value={item.course_name}>{item.course_name} ({item.count})</option>)}
              </select>
            </label>
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Módulo
              <select value={module} disabled={!course} onChange={(event) => { setModule(event.target.value); setClassTitle(""); setRevealed(false); }} className="mt-1.5 w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2.5 text-sm font-normal normal-case text-slate-200 outline-none disabled:opacity-40">
                <option value="">Todos los módulos</option>{selectedCourse?.modules.map((item) => <option key={item.module_name} value={item.module_name}>{item.module_name} ({item.count})</option>)}
              </select>
            </label>
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Clase
              <select value={classTitle} disabled={!module} onChange={(event) => { setClassTitle(event.target.value); setRevealed(false); }} className="mt-1.5 w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2.5 text-sm font-normal normal-case text-slate-200 outline-none disabled:opacity-40">
                <option value="">Todas las clases</option>{selectedModule?.classes.map((item) => <option key={item.class_title} value={item.class_title}>{item.class_title} ({item.count})</option>)}
              </select>
            </label>
          </div>
          <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
          <div className="flex rounded-xl border border-slate-800 bg-slate-900 p-1"><button onClick={() => { setMode("library"); setRevealed(false); }} className={`rounded-lg px-4 py-2 text-xs font-bold ${mode === "library" ? "bg-violet-500/20 text-violet-200" : "text-slate-500"}`}>Biblioteca</button><button onClick={() => { setMode("study"); setRevealed(false); }} className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold ${mode === "study" ? "bg-violet-500/20 text-violet-200" : "text-slate-500"}`}><Play className="h-3.5 w-3.5" /> Estudiar</button></div>
          {mode === "library" && <label className="flex w-full items-center gap-2 rounded-xl border border-slate-800 bg-slate-900 px-3 md:max-w-sm"><Search className="h-4 w-4 text-slate-500" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar pregunta o respuesta" className="w-full bg-transparent py-2.5 text-sm outline-none placeholder:text-slate-600" /></label>}
          {mode === "library" && <div className="relative"><button onClick={() => setStateMenuOpen((value) => !value)} className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900 px-3 py-2.5 text-xs font-bold text-slate-300 md:w-44"><span>{visibleStates.active && visibleStates.inactive ? "Activas e inactivas" : visibleStates.active ? "Solo activas" : "Solo inactivas"}</span><ChevronDown className="h-4 w-4" /></button>{stateMenuOpen && <div className="absolute right-0 z-30 mt-2 w-52 rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-2xl"><label className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-slate-800"><input type="checkbox" checked={visibleStates.active} onChange={() => toggleVisibleState("active")} className="accent-violet-500" /> Activas</label><label className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-slate-800"><input type="checkbox" checked={visibleStates.inactive} onChange={() => toggleVisibleState("inactive")} className="accent-violet-500" /> Inactivas ({summary.inactive})</label><p className="px-3 pb-1 pt-2 text-[10px] text-slate-600">Debe quedar al menos una opción.</p></div>}</div>}
          </div>
        </div>

        {mode === "study" ? (
          <StudyCard card={current} revealed={revealed} busy={busy} onReveal={() => setRevealed((value) => !value)} onRate={(rating) => void review(rating)} />
        ) : (
          <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50">
            <div className="divide-y divide-slate-800">{cards.map((card) => <LibraryCard key={card.id} card={card} onEdit={() => setEditing(card)} onToggle={async () => { await api(`/api/flashcards/${card.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: !card.is_active }) }); await refresh(); }} />)}{cards.length === 0 && <div className="py-20 text-center text-sm text-slate-500">No hay tarjetas para estos filtros.</div>}</div>
          </section>
        )}
      </div>
      <FlashcardsSidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} tree={tree} course={course} module={module} classTitle={classTitle} onSelect={(nextCourse, nextModule, nextClass) => { setCourse(nextCourse); setModule(nextModule); setClassTitle(nextClass); setRevealed(false); }} />
      <NavigationDock />
      {editing && <EditModal card={editing} onClose={() => setEditing(null)} onSave={async (question, answer) => { setBusy(true); try { await api(`/api/flashcards/${editing.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, answer }) }); setEditing(null); await refresh(); } finally { setBusy(false); } }} />}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4"><p className="text-[10px] font-bold uppercase tracking-widest text-slate-600">{label}</p><p className={`mt-2 text-2xl font-black ${tone}`}>{value}</p></div>; }

const maturityLabels = { new: "Nueva", learning: "Aprendiendo", young: "Joven", mature: "Madura" };

function LibraryCard({ card, onEdit, onToggle }: { card: Card; onEdit: () => void; onToggle: () => void }) { return <article className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center"><div className="min-w-0 flex-1"><div className="mb-1 flex items-center gap-2"><span className="rounded-full bg-slate-800 px-2 py-0.5 text-[9px] font-bold uppercase text-slate-400">{maturityLabels[card.maturity]}</span>{card.interval_days > 0 && <span className="text-[10px] text-slate-600">Intervalo: {card.interval_days} días</span>}<span className="truncate text-[10px] text-slate-600">{card.course_module} · {card.class_title}</span></div><h3 className="text-sm font-bold text-slate-200">{card.question}</h3><p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-500">{card.answer}</p></div><div className="flex gap-2"><button onClick={onEdit} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-white"><Edit3 className="h-4 w-4" /></button><button onClick={onToggle} className="rounded-lg border border-slate-700 p-2 text-slate-400">{card.is_active ? <ToggleRight className="h-4 w-4 text-emerald-400" /> : <ToggleLeft className="h-4 w-4" />}</button></div></article>; }

function StudyCard({ card, revealed, busy, onReveal, onRate }: { card?: Card; revealed: boolean; busy: boolean; onReveal: () => void; onRate: (rating: number) => void }) {
  if (!card) return <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/5 py-24 text-center"><h2 className="text-xl font-bold text-emerald-300">Sesión terminada</h2><p className="mt-2 text-sm text-slate-500">No quedan tarjetas pendientes con estos filtros.</p></div>;
  const colors = ["rose", "amber", "cyan", "emerald"] as const;
  return <section className="mx-auto max-w-3xl rounded-3xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl md:p-10"><p className="mb-7 text-center text-[10px] uppercase tracking-widest text-slate-600">{card.course_module} · {card.class_title}</p><h2 className="min-h-28 text-center text-xl font-bold leading-relaxed md:text-2xl">{card.question}</h2><button onClick={onReveal} className="mx-auto mt-7 flex items-center gap-2 rounded-xl border border-violet-500/30 bg-violet-500/10 px-5 py-2.5 text-sm font-bold text-violet-200">{revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}{revealed ? "Ocultar respuesta" : "Mostrar respuesta"}</button>{revealed && <><div className="mt-8 rounded-2xl border border-slate-700 bg-slate-950/60 p-6 text-center text-sm leading-7 text-slate-300">{card.answer}</div><p className="mt-6 text-center text-xs text-slate-500">Elige según qué tan bien recordaste la respuesta. Cada opción programa el próximo repaso.</p><div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">{card.review_options.map((option, index) => <Rate key={option.rating} label={option.label} meaning={option.meaning} dueLabel={option.due_label} color={colors[index]} disabled={busy} onClick={() => onRate(option.rating)} />)}</div></>}</section>;
}

function Rate({ label, meaning, dueLabel, color, disabled, onClick }: { label: string; meaning: string; dueLabel: string; color: "rose" | "amber" | "cyan" | "emerald"; disabled: boolean; onClick: () => void }) { const colors = { rose: "border-rose-500/30 text-rose-300", amber: "border-amber-500/30 text-amber-300", cyan: "border-cyan-500/30 text-cyan-300", emerald: "border-emerald-500/30 text-emerald-300" }; return <button disabled={disabled} onClick={onClick} className={`rounded-xl border p-3 text-xs font-bold disabled:opacity-40 ${colors[color]}`}>{label}<span className="mt-1 block min-h-7 text-[9px] font-normal text-slate-400">{meaning}</span><span className="mt-1 block text-[10px]">Próximo: {dueLabel}</span></button>; }

function EditModal({ card, onClose, onSave }: { card: Card; onClose: () => void; onSave: (question: string, answer: string) => Promise<void> }) { const [question, setQuestion] = useState(card.question); const [answer, setAnswer] = useState(card.answer); return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/75 p-4"><div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 p-5"><h2 className="font-bold">Editar flashcard</h2><p className="mt-1 text-xs text-slate-500">La representación Markdown compatible también será actualizada.</p><label className="mt-5 block text-xs text-slate-400">Pregunta<textarea value={question} onChange={(event) => setQuestion(event.target.value)} className="mt-2 min-h-24 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-sm text-white outline-none" /></label><label className="mt-4 block text-xs text-slate-400">Respuesta<textarea value={answer} onChange={(event) => setAnswer(event.target.value)} className="mt-2 min-h-32 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-sm text-white outline-none" /></label><div className="mt-5 flex justify-end gap-2"><button onClick={onClose} className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-bold">Cancelar</button><button onClick={() => void onSave(question, answer)} disabled={!question.trim() || !answer.trim()} className="rounded-xl bg-violet-600 px-4 py-2 text-xs font-bold disabled:opacity-40">Guardar</button></div></div></div>; }
