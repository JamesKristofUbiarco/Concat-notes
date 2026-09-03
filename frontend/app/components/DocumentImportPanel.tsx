"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Check, Loader2, Upload } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Job = { id: string; status: string; stage: string; progress: number; message: string; error?: string; warnings: string[] };
type DocumentInfo = { id: string; filename: string; format: "pdf" | "epub"; title: string; author: string; page_count: number | null; status: string; capabilities: Record<string, unknown>; warnings: string[]; latest_job?: Job };
type Section = { id: string; title: string; level: number; page_start: number | null; page_end: number | null; confidence: number; children: Section[] };
type Asset = { id: string; url: string; description: string };
type Draft = { id: string; title: string; page_ranges: Array<{ start: number; end: number }>; source_markdown: string; course_name: string; course_module: string; class_title: string; assets: Asset[]; confirmed: boolean };
type Run = { id: string; status: string; estimated_cost_usd: number; actual_cost_usd: number; warnings: string[]; drafts: Draft[] };
type PagePreview = { page: number; thumbnail_url: string | null };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "No se pudo completar la operación.");
  }
  return response.json() as Promise<T>;
}

function flatten(nodes: Section[], ancestors: string[] = []): Array<{ section: Section; ancestors: string[] }> {
  return nodes.flatMap((section) => [{ section, ancestors }, ...flatten(section.children, [...ancestors, section.id])]);
}

export function DocumentImportPanel({ courses, onConfirmed }: { courses: string[]; onConfirmed: () => Promise<unknown> }) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [document, setDocument] = useState<DocumentInfo | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [selectedSections, setSelectedSections] = useState<Set<string>>(new Set());
  const [excludedSections, setExcludedSections] = useState<Set<string>>(new Set());
  const [selectionMode, setSelectionMode] = useState<"full" | "sections" | "pages">("full");
  const [ranges, setRanges] = useState("1-10");
  const [profile, setProfile] = useState<"local" | "balanced" | "accurate">("balanced");
  const [myNotes, setMyNotes] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [pagePreviews, setPagePreviews] = useState<PagePreview[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadDocuments = useCallback(async () => setDocuments(await api<DocumentInfo[]>("/api/documents")), []);
  useEffect(() => { const timer = window.setTimeout(() => void loadDocuments(), 0); return () => window.clearTimeout(timer); }, [loadDocuments]);

  const selectDocument = useCallback(async (id: string) => {
    const next = await api<DocumentInfo>(`/api/documents/${id}`);
    setDocument(next); setJob(next.latest_job || null); setRun(null); setRunId(""); setError("");
    if (next.status === "ready") setSections(await api<Section[]>(`/api/documents/${id}/sections`));
  }, []);

  useEffect(() => {
    if (!job || !["pending", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      const next = await api<Job>(`/api/document-jobs/${job.id}`).catch(() => null);
      if (!next) return;
      setJob(next);
      if (next.status === "completed" && document) {
        const refreshed = await api<DocumentInfo>(`/api/documents/${document.id}`);
        setDocument(refreshed);
        if (refreshed.status === "ready") setSections(await api<Section[]>(`/api/documents/${document.id}/sections`));
        if (runId) setRun(await api<Run>(`/api/documents/${document.id}/runs/${runId}`));
        void loadDocuments();
      }
      if (next.status === "failed") setError(next.error || "El trabajo documental falló.");
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job, document, runId, loadDocuments]);

  useEffect(() => {
    if (!document || selectionMode !== "pages" || document.format !== "pdf") return;
    const timer = window.setTimeout(() => void api<PagePreview[]>(`/api/documents/${document.id}/pages?page_from=1&page_to=30`).then(setPagePreviews).catch(() => setPagePreviews([])), 0);
    return () => window.clearTimeout(timer);
  }, [document, selectionMode]);

  const uploadDocument = async (file?: File) => {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", file);
      const result = await api<{ document: DocumentInfo; job: Job }>("/api/documents", { method: "POST", body });
      setDocument(result.document); setJob(result.job); setRun(null); await loadDocuments();
      if (result.document.status === "ready") setSections(await api(`/api/documents/${result.document.id}/sections`));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo subir el documento."); }
    finally { setBusy(false); }
  };

  const parsedRanges = useMemo(() => ranges.split(",").map((value) => value.trim()).filter(Boolean).map((value) => {
    const [start, end] = value.split("-").map(Number); return { start, end: end || start };
  }).filter((item) => Number.isInteger(item.start) && Number.isInteger(item.end)), [ranges]);

  const processDocument = async (approved = 1) => {
    if (!document) return;
    setBusy(true); setError("");
    const selection = selectionMode === "full" ? { mode: "full" } : selectionMode === "pages"
      ? { mode: "pages", ranges: parsedRanges }
      : { mode: "sections", section_ids: [...selectedSections], include_descendants: true, excluded_section_ids: [...excludedSections] };
    try {
      const result = await api<{ run_id: string; job: Job; estimated_cost_usd: number }>(`/api/documents/${document.id}/process`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ selection, profile, approved_cost_usd: approved }),
      });
      setRunId(result.run_id); setJob(result.job); setRun(null);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "No se pudo iniciar la extracción.";
      const amount = Number(message.match(/US\$(\d+(?:\.\d+)?)/)?.[1]);
      if (amount > 1 && window.confirm(`${message}\n\n¿Autorizar hasta US$${amount.toFixed(2)} para esta ejecución?`)) {
        setBusy(false); await processDocument(amount); return;
      }
      setError(message);
    } finally { setBusy(false); }
  };

  const updateDraft = (id: string, field: keyof Draft, value: string) => setRun((current) => current ? { ...current, drafts: current.drafts.map((draft) => draft.id === id ? { ...draft, [field]: value } : draft) } : current);

  const confirm = async () => {
    if (!document || !run) return;
    setBusy(true); setError("");
    try {
      await api(`/api/documents/${document.id}/runs/${run.id}/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ my_notes: myNotes, drafts: run.drafts.map(({ id, course_name, course_module, class_title, source_markdown }) => ({ id, course_name, course_module, class_title, source_markdown })) }),
      });
      await onConfirmed(); setRun({ ...run, drafts: run.drafts.map((draft) => ({ ...draft, confirmed: true })) });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudieron crear las notas."); }
    finally { setBusy(false); }
  };

  const toggleSection = (section: Section, ancestors: string[]) => {
    const inherited = ancestors.some((id) => selectedSections.has(id));
    if (inherited && !selectedSections.has(section.id)) {
      setExcludedSections((current) => { const next = new Set(current); if (next.has(section.id)) next.delete(section.id); else next.add(section.id); return next; });
      return;
    }
    setSelectedSections((current) => { const next = new Set(current); if (next.has(section.id)) next.delete(section.id); else next.add(section.id); return next; });
    setExcludedSections((current) => { const next = new Set(current); next.delete(section.id); return next; });
  };

  return <section className="col-span-full space-y-5 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 md:p-7">
    <div className="flex flex-col justify-between gap-4 border-b border-slate-800 pb-5 md:flex-row md:items-center">
      <div><h2 className="flex items-center gap-2 text-lg font-bold"><BookOpen className="h-5 w-5 text-indigo-400" /> Importar PDF o EPUB</h2><p className="mt-1 text-xs text-slate-500">La estructura se detecta localmente; tú decides qué contenido enviar a la cola de notas.</p></div>
      <label className="flex cursor-pointer items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-bold hover:bg-indigo-500"><Upload className="h-4 w-4" />{busy ? "Subiendo…" : "Subir documento"}<input type="file" accept=".pdf,.epub,application/pdf,application/epub+zip" className="hidden" disabled={busy} onChange={(event) => void uploadDocument(event.target.files?.[0])} /></label>
    </div>
    <label className="block text-sm font-medium text-slate-300">Notas propias <span className="font-normal text-slate-500">(opcional)</span><textarea value={myNotes} onChange={(event) => setMyNotes(event.target.value)} placeholder="Escribe aquí tus observaciones, ideas o contexto sobre el documento." className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm leading-6 text-slate-200 outline-none focus:border-indigo-500/60" /><span className="mt-2 block text-xs font-normal text-slate-500">Se añadirán a las notas creadas a partir de este documento.</span></label>
    {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
      <aside className="space-y-2"><p className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Documentos</p>{documents.map((item) => <button key={item.id} onClick={() => void selectDocument(item.id)} className={`w-full rounded-xl border p-3 text-left ${document?.id === item.id ? "border-indigo-500/50 bg-indigo-500/10" : "border-slate-800 bg-slate-950/40"}`}><p className="truncate text-xs font-bold">{item.title || item.filename}</p><p className="mt-1 text-[10px] uppercase text-slate-600">{item.format} · {item.status}</p></button>)}{documents.length === 0 && <p className="py-8 text-center text-xs text-slate-600">Aún no hay documentos.</p>}</aside>
      <div className="min-w-0">
        {!document && <div className="rounded-xl border border-dashed border-slate-700 py-20 text-center text-sm text-slate-500">Sube o selecciona un documento para comenzar.</div>}
        {document && <div className="space-y-5">
          <div><h3 className="font-bold">{document.title}</h3><p className="mt-1 text-xs text-slate-500">{document.author || "Autor no declarado"}{document.page_count ? ` · ${document.page_count} páginas físicas` : " · EPUB refluible"}</p>{document.warnings?.map((warning) => <p key={warning} className="mt-2 text-xs text-amber-400">⚠ {warning}</p>)}</div>
          {job && ["pending", "running"].includes(job.status) && <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4"><div className="flex items-center gap-2 text-sm font-bold"><Loader2 className="h-4 w-4 animate-spin text-indigo-400" />{job.message}</div><div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full bg-indigo-500 transition-all" style={{ width: `${job.progress}%` }} /></div><p className="mt-2 text-[10px] uppercase text-slate-600">{job.stage} · {job.progress}%</p></div>}
          {document.status === "ready" && !run && <>
            <div className="flex flex-wrap gap-2">{(["full", "sections", ...(document.format === "pdf" ? ["pages"] : [])] as Array<"full" | "sections" | "pages">).map((mode) => <button key={mode} onClick={() => setSelectionMode(mode)} className={`rounded-xl px-4 py-2 text-xs font-bold ${selectionMode === mode ? "bg-indigo-500/20 text-indigo-300" : "bg-slate-950 text-slate-500"}`}>{mode === "full" ? "Documento completo" : mode === "sections" ? "Capítulos" : "Páginas"}</button>)}</div>
            {selectionMode === "sections" && <div className="max-h-80 overflow-auto rounded-xl border border-slate-800 p-3">{flatten(sections).map(({ section, ancestors }) => { const inherited = ancestors.some((id) => selectedSections.has(id)); const checked = (selectedSections.has(section.id) || inherited) && !excludedSections.has(section.id); return <div key={section.id} style={{ paddingLeft: `${(section.level - 1) * 18}px` }} className="flex items-center gap-2 py-1.5"><input type="checkbox" checked={checked} onChange={() => toggleSection(section, ancestors)} className="accent-indigo-500" /><span className="min-w-0 flex-1 truncate text-sm">{section.title}</span>{inherited && !selectedSections.has(section.id) && <span className="text-[9px] text-indigo-400">incluido</span>}{section.page_start && <span className="text-[10px] text-slate-600">p. {section.page_start}-{section.page_end}</span>}</div>; })}</div>}
            {selectionMode === "pages" && <div><label className="block text-xs text-slate-400">Rangos físicos del PDF<input value={ranges} onChange={(event) => setRanges(event.target.value)} placeholder="1-10, 15, 20-25" className="mt-2 w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm outline-none" /></label>{pagePreviews.length > 0 && <div className="mt-3 grid max-h-56 grid-cols-4 gap-2 overflow-auto md:grid-cols-8">{pagePreviews.map((page) => <button key={page.page} onClick={() => setRanges(String(page.page))} className="overflow-hidden rounded-lg border border-slate-800 bg-slate-950 text-[9px] text-slate-500">{page.thumbnail_url ? <img src={page.thumbnail_url} alt={`Página ${page.page}`} className="h-20 w-full object-contain" /> : <div className="flex h-20 items-center justify-center">Sin vista</div>}<span className="block py-1">p. {page.page}</span></button>)}</div>}</div>}
            <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end"><label className="text-xs text-slate-400">Perfil<select value={profile} onChange={(event) => setProfile(event.target.value as typeof profile)} className="mt-2 w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm"><option value="local">Local — sin visión remota</option><option value="balanced">Equilibrado — sólo visuales relevantes</option><option value="accurate">Preciso — análisis visual ampliado</option></select></label><button disabled={busy || (selectionMode === "sections" && selectedSections.size === 0)} onClick={() => void processDocument()} className="rounded-xl bg-violet-600 px-5 py-3 text-xs font-bold disabled:opacity-40">Extraer selección</button></div>
          </>}
          {run && <div className="space-y-5"><div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-xs text-emerald-200">Extracción fiel lista · coste visual real US${run.actual_cost_usd.toFixed(4)}. Revisa los metadatos antes de crear las notas.</div>{run.drafts.map((draft) => <article key={draft.id} className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4"><div className="grid gap-3 md:grid-cols-3"><label className="text-[10px] uppercase text-slate-600">Curso<input list="document-courses" value={draft.course_name} onChange={(e) => updateDraft(draft.id, "course_name", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-900 p-2 text-xs normal-case text-white" /></label><label className="text-[10px] uppercase text-slate-600">Módulo<input value={draft.course_module} onChange={(e) => updateDraft(draft.id, "course_module", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-900 p-2 text-xs normal-case text-white" /></label><label className="text-[10px] uppercase text-slate-600">Clase<input value={draft.class_title} onChange={(e) => updateDraft(draft.id, "class_title", e.target.value)} className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-900 p-2 text-xs normal-case text-white" /></label></div><textarea value={draft.source_markdown} onChange={(e) => updateDraft(draft.id, "source_markdown", e.target.value)} className="mt-4 min-h-64 w-full rounded-xl border border-slate-800 bg-slate-900 p-4 font-mono text-xs leading-6 text-slate-300" />{draft.assets.length > 0 && <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">{draft.assets.map((asset) => <figure key={asset.id}><img src={asset.url} alt={asset.description || "Figura documental"} className="h-28 w-full rounded-lg object-contain bg-black" /><figcaption className="mt-1 line-clamp-2 text-[9px] text-slate-600">{asset.description || "Sin análisis visual"}</figcaption></figure>)}</div>}</article>)}<datalist id="document-courses">{courses.map((course) => <option key={course} value={course} />)}</datalist><div className="flex justify-end"><button disabled={busy || run.drafts.every((draft) => draft.confirmed)} onClick={() => void confirm()} className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-xs font-bold disabled:opacity-40"><Check className="h-4 w-4" /> Crear {run.drafts.length} nota(s) en la cola</button></div></div>}
        </div>}
      </div>
    </div>
  </section>;
}
