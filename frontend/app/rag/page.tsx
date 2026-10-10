"use client";

import { useCallback, useEffect, useState } from "react";
import { Database, RefreshCw, Search, X } from "lucide-react";
import { NavigationDock } from "../components/NavigationDock";
import { jsonRequest, maintenanceRequest, MaintenanceClass } from "../lib/maintenanceApi";

type Kind = "note" | "source" | "claim" | "flashcard";
const labels: Record<Kind, string> = { note: "Notas procesadas", source: "Fuentes originales", claim: "Afirmaciones", flashcard: "Flashcards" };
interface Chunk { kind: Kind; id: string; note_id: string; course: string; class_title: string; preview: string; chars: number; has_embedding: boolean }
interface Detail { kind: Kind; id: string; content: string; digest: string; embedding: number[]; has_embedding: boolean; editable: boolean; source_type: string | null; concept: string | null; evidence: string | null }
interface Stats { counts: Record<Kind, { total: number; real: number; missing: number }>; embedding_configured: boolean }
const keyOf = (item: { kind: Kind; id: string }) => `${item.kind}:${item.id}`;
const control = "w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm focus:ring-2 focus:ring-indigo-400";

export default function RagPage() {
  const [classes, setClasses] = useState<MaintenanceClass[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [items, setItems] = useState<Chunk[]>([]);
  const [total, setTotal] = useState(0);
  const [course, setCourse] = useState("");
  const [noteId, setNoteId] = useState("");
  const [kind, setKind] = useState("");
  const [embedding, setEmbedding] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<Detail | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadSummary = useCallback(async () => {
    const [nextClasses, nextStats] = await Promise.all([
      maintenanceRequest<MaintenanceClass[]>("/rag/classes"), maintenanceRequest<Stats>("/rag/stats"),
    ]);
    setClasses(nextClasses); setStats(nextStats);
  }, []);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "25", embedding, search });
      if (course) params.set("course", course);
      if (noteId) params.set("note_id", noteId);
      if (kind) params.set("kind", kind);
      const result = await maintenanceRequest<{ items: Chunk[]; total: number }>(`/rag/chunks?${params}`);
      setItems(result.items); setTotal(result.total);
      setSelected(previous => new Set([...previous].filter(key => result.items.some(item => keyOf(item) === key))));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo consultar el RAG."); }
    finally { setLoading(false); }
  }, [page, embedding, search, course, noteId, kind]);
  useEffect(() => { const timer = window.setTimeout(() => void loadSummary().catch(reason => setError(String(reason))), 0); return () => window.clearTimeout(timer); }, [loadSummary]);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 250); return () => window.clearTimeout(timer); }, [load]);

  const filterChanged = () => { setPage(1); setSelected(new Set()); };
  const open = async (item: Chunk) => {
    setError("");
    try { const next = await maintenanceRequest<Detail>(`/rag/chunks/${item.kind}/${item.id}`); setDetail(next); setDraft(next.content); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo abrir el fragmento."); }
  };
  const save = async () => {
    if (!detail) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await maintenanceRequest<{ has_embedding: boolean }>(`/rag/chunks/${detail.kind}/${detail.id}`, { ...jsonRequest({ content: draft, digest: detail.digest }), method: "PUT" });
      setNotice(result.has_embedding ? "Fragmento guardado y embedding actualizado." : "Fragmento guardado. Quedó sin embedding real; puedes regenerarlo cuando la API esté disponible.");
      setDetail(null); await Promise.all([load(), loadSummary()]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo guardar."); }
    finally { setBusy(false); }
  };
  const action = async (name: "delete_chunks" | "delete_embeddings" | "reembed") => {
    const targets = items.filter(item => selected.has(keyOf(item))).map(({ kind, id }) => ({ kind, id }));
    if (!targets.length) return;
    const message = name === "delete_chunks" ? `¿Borrar ${targets.length} fragmentos del índice RAG? Las notas originales se conservarán. Una reindexación puede volver a crearlos.` : name === "delete_embeddings" ? `¿Borrar ${targets.length} embeddings? Los textos seguirán disponibles para búsqueda por palabras, pero perderán su vector semántico.` : `¿Regenerar ${targets.length} embeddings con VoyageAI? Esta operación utiliza su API.`;
    if (!window.confirm(message)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await maintenanceRequest<{ affected: number }>("/rag/actions", jsonRequest({ action: name, targets }));
      setSelected(new Set()); setDetail(null); setNotice(`${result.affected} elementos actualizados.`);
      await Promise.all([load(), loadSummary()]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo completar la acción."); }
    finally { setBusy(false); }
  };
  const courses = Array.from(new Set(classes.map(item => item.course))).sort();
  const hasCards = items.some(item => item.kind === "flashcard" && selected.has(keyOf(item)));

  return <div className="min-h-screen bg-slate-950 text-slate-100 px-4 py-8 pb-32 md:px-8">
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="flex items-start justify-between gap-4 border-b border-slate-800 pb-6"><div><h1 className="flex items-center gap-3 text-3xl font-bold"><Database className="h-7 w-7 text-indigo-400" />Memoria RAG</h1><p className="mt-2 text-sm text-slate-400">Inspecciona y corrige los fragmentos que el agente recupera para generar notas.</p></div><button disabled={busy} onClick={() => { setError(""); void Promise.all([load(), loadSummary()]).catch(reason => setError(String(reason))); }} className="rounded-lg border border-slate-700 p-3 cursor-pointer" aria-label="Actualizar RAG"><RefreshCw className="h-4 w-4" /></button></header>
      {stats && <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{(Object.keys(labels) as Kind[]).map(type => <div key={type} className="rounded-xl border border-slate-800 bg-slate-900 p-4"><p className="text-xs text-slate-400">{labels[type]}</p><p className="mt-2 text-2xl font-bold">{stats.counts[type].total}</p><p className="mt-1 text-xs text-slate-500">{stats.counts[type].real} con vector · {stats.counts[type].missing} pendientes</p></div>)}</div>}
      {stats && !stats.embedding_configured && <p className="text-sm text-amber-300">La API de VoyageAI no está configurada. Los fragmentos se pueden consultar y editar; generar vectores requiere configurar la API.</p>}
      {error && <p role="alert" className="rounded-xl bg-rose-950/50 p-4 text-rose-300">{error}</p>}
      {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 h-fit">
          <h2 className="font-semibold">Filtros</h2>
          <label className="block text-xs text-slate-400">Curso<select value={course} onChange={event => { setCourse(event.target.value); setNoteId(""); filterChanged(); }} className={`${control} mt-2`}><option value="">Todos los cursos</option>{courses.map(name => <option key={name}>{name}</option>)}</select></label>
          <label className="block text-xs text-slate-400">Clase<select value={noteId} onChange={event => { setNoteId(event.target.value); filterChanged(); }} className={`${control} mt-2`}><option value="">Todas las clases</option>{classes.filter(item => !course || item.course === course).map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
          <label className="block text-xs text-slate-400">Tipo de fragmento<select value={kind} onChange={event => { setKind(event.target.value); filterChanged(); }} className={`${control} mt-2`}><option value="">Todos los tipos</option>{(Object.keys(labels) as Kind[]).map(type => <option key={type} value={type}>{labels[type]}</option>)}</select></label>
          <label className="block text-xs text-slate-400">Embedding<select value={embedding} onChange={event => { setEmbedding(event.target.value); filterChanged(); }} className={`${control} mt-2`}><option value="all">Todos</option><option value="real">Con vector real</option><option value="missing">Sin vector real</option></select></label>
          <p className="text-xs text-slate-500 leading-relaxed">Las ediciones afectan a la memoria del agente. Para cambiar una nota o una tarjeta, usa su sección correspondiente. Al regenerar o reindexar una clase se reconstruyen sus fragmentos.</p>
        </aside>
        <section className="min-w-0 space-y-4">
          <label className="flex items-center gap-2"><Search className="h-4 w-4 text-slate-400" /><input value={search} onChange={event => { setSearch(event.target.value); filterChanged(); }} aria-label="Buscar en fragmentos" placeholder="Buscar texto dentro del RAG" className={control} /></label>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" disabled={busy || loading} checked={items.length > 0 && items.every(item => selected.has(keyOf(item)))} onChange={event => setSelected(event.target.checked ? new Set(items.map(keyOf)) : new Set())} />Seleccionar página</label>
            <span className="text-slate-400">{selected.size} seleccionados · {total} resultados</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button disabled={busy || loading || !selected.size || !stats?.embedding_configured} onClick={() => void action("reembed")} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Regenerar embeddings</button>
            <button disabled={busy || loading || !selected.size} onClick={() => void action("delete_embeddings")} className="rounded-lg border border-slate-700 px-3 py-2 text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Borrar embeddings</button>
            <button title={hasCards ? "Las tarjetas se borran desde Flashcards" : undefined} disabled={busy || loading || !selected.size || hasCards} onClick={() => void action("delete_chunks")} className="rounded-lg border border-rose-500/50 text-rose-300 px-3 py-2 text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Borrar fragmentos</button>
          </div>
          {loading && <p role="status" className="text-sm text-slate-400">Cargando fragmentos…</p>}
          {!loading && !items.length && <p className="rounded-xl border border-slate-800 p-6 text-slate-500">No hay fragmentos para estos filtros.</p>}
          {!loading && items.map(item => <article key={keyOf(item)} className="flex gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <input type="checkbox" aria-label={`Seleccionar fragmento de ${item.class_title}`} checked={selected.has(keyOf(item))} disabled={busy} className="self-start mt-1" onChange={() => setSelected(previous => { const next = new Set(previous); const key = keyOf(item); if (next.has(key)) next.delete(key); else next.add(key); return next; })} />
            <button onClick={() => void open(item)} className="min-w-0 flex-1 text-left cursor-pointer focus:ring-2 focus:ring-indigo-400 rounded-lg">
              <div className="flex flex-wrap gap-2 text-xs"><span className="text-indigo-300">{labels[item.kind]}</span><span className={item.has_embedding ? "text-emerald-300" : "text-amber-300"}>{item.has_embedding ? "Vector real" : "Sin vector real"}</span><span className="text-slate-500">{item.chars} caracteres</span></div>
              <h3 className="mt-2 text-sm font-semibold">{item.class_title}</h3><p className="text-xs text-slate-500">{item.course}</p><p className="mt-3 text-sm text-slate-400 whitespace-pre-wrap break-words">{item.preview}{item.chars > 280 ? "…" : ""}</p>
            </button>
          </article>)}
          <div className="flex items-center justify-between text-sm"><button disabled={page === 1 || loading} onClick={() => { setSelected(new Set()); setPage(value => value - 1); }} className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40 cursor-pointer">Anterior</button><span className="text-slate-400">Página {page} de {Math.max(1, Math.ceil(total / 25))}</span><button disabled={page * 25 >= total || loading} onClick={() => { setSelected(new Set()); setPage(value => value + 1); }} className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40 cursor-pointer">Siguiente</button></div>
        </section>
      </div>
    </div>
    {detail && <div className="fixed inset-0 z-[60] flex justify-end bg-black/60" onClick={() => { if (!busy) setDetail(null); }}>
      <section role="dialog" aria-modal="true" aria-label="Detalle del fragmento" className="h-full w-full max-w-2xl overflow-y-auto bg-slate-900 p-5 md:p-8 space-y-4" onClick={event => event.stopPropagation()}>
        <div className="flex justify-between items-center"><h2 className="text-xl font-bold">{labels[detail.kind]}</h2><button disabled={busy} onClick={() => setDetail(null)} aria-label="Cerrar detalle" className="rounded-lg p-2 hover:bg-slate-800 cursor-pointer"><X className="h-5 w-5" /></button></div>
        <p className="text-sm text-slate-400">{detail.has_embedding ? "Embedding real" : "Sin embedding real"} · {detail.embedding.length} dimensiones</p>
        {detail.source_type && <p className="text-xs text-slate-400">Fuente: {detail.source_type}</p>}
        {detail.concept && <p className="text-sm font-semibold">{detail.concept}</p>}
        <label className="block text-sm">Contenido<textarea autoFocus value={draft} readOnly={!detail.editable} onChange={event => setDraft(event.target.value)} rows={18} className={`${control} mt-2 font-mono`} /></label>
        {detail.editable ? <><p className="text-xs text-slate-400">Guardar actualiza el fragmento del RAG y solicita un nuevo embedding. Si la API falla, el texto se guarda con el vector pendiente.</p><button disabled={busy || !draft.trim() || draft === detail.content} onClick={() => void save()} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm cursor-pointer disabled:opacity-40">{busy ? "Guardando…" : "Guardar y actualizar embedding"}</button></> : <p className="text-sm text-slate-400">Edita el contenido de esta tarjeta en la sección Flashcards.</p>}
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        {detail.evidence && <details><summary className="cursor-pointer text-sm">Evidencia original</summary><p className="mt-2 whitespace-pre-wrap text-sm text-slate-400">{detail.evidence}</p></details>}
        <details><summary className="cursor-pointer text-sm">Ver vector completo</summary><pre className="mt-3 max-h-64 overflow-auto rounded-lg bg-slate-950 p-3 text-xs whitespace-pre-wrap break-all">{JSON.stringify(detail.embedding)}</pre></details>
      </section>
    </div>}
    <NavigationDock />
  </div>;
}
