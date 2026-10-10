"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, Search, Sparkles } from "lucide-react";
import { componentLabels, Component, GenerationRequest, jsonRequest, MaintenanceClass, maintenanceRequest, RegenerationJob } from "../lib/maintenanceApi";

const statusLabels: Record<string, string> = { pending: "En espera", running: "Generando", complete: "Completado", failed: "Falló" };
const phaseLabels: Record<string, string> = { context: "Consultando el historial", evidence: "Extrayendo evidencia y comparando con clases anteriores", coverage: "Revisando cobertura", content: "Redactando contenido", diagrams: "Revisando diagramas", glossary: "Generando glosario", flashcards: "Generando flashcards", supplements: "Generando glosario y flashcards en paralelo", assembly: "Ensamblando nota", saving: "Guardando nota e índices", complete: "Completado" };
const duration = (milliseconds: number) => milliseconds < 60000 ? `${(milliseconds / 1000).toFixed(1)} s` : `${Math.floor(milliseconds / 60000)} min ${Math.floor(milliseconds / 1000) % 60} s`;

function RequestProgress({ requests, running, now }: { requests: GenerationRequest[]; running: boolean; now: number }) {
  const latest = new Map<string, GenerationRequest>();
  for (const request of requests) latest.set(request.phase, request);
  return <div className="space-y-1 rounded-lg border border-slate-800 p-2">
    {Array.from(latest.values()).map(request => {
      const active = running && ["waiting", "generating"].includes(request.status);
      const elapsed = active && now ? Math.max(request.elapsed_ms, now - Date.parse(request.started_at)) : request.elapsed_ms;
      const labels = { waiting: "Esperando contenido", generating: "Recibiendo contenido", complete: "Respuesta recibida", timeout: "Límite alcanzado", error: "Llamada fallida" };
      const timeoutLabels = { total: "tiempo total", first_response: "sin primer texto", idle: "sin avance" };
      return <p key={request.id} className={active ? "text-indigo-300" : "text-slate-400"}>
        {phaseLabels[request.phase] || (request.phase === "content_repair" ? "Ajustando formato" : "Comparando evidencia")} · {request.model_name} · {labels[request.status]}
        {request.timeout_kind && ` (${timeoutLabels[request.timeout_kind]})`}
        {` · ${duration(elapsed)} · Tope por llamada: ${duration(request.deadline_s * 1000)}`}
        {(request.status === "waiting" || request.timeout_kind === "first_response") && ` · Máximo sin primer texto: ${duration(request.first_response_limit_s * 1000)}`}
        {(request.status === "generating" || request.timeout_kind === "idle") && ` · Máximo sin avance: ${duration(request.idle_limit_s * 1000)}`}
        {request.first_token_ms !== undefined && ` · Primer texto: ${duration(request.first_token_ms)}`}
        {request.output_chars > 0 && ` · ${request.output_chars.toLocaleString()} caracteres recibidos`}
        {active && request.last_output_at && now > 0 && ` · Último avance hace ${duration(Math.max(0, now - Date.parse(request.last_output_at)))}`}
      </p>;
    })}
  </div>;
}

export function ClassRegenerationPanel({ onChanged }: { onChanged: () => Promise<void> }) {
  const [classes, setClasses] = useState<MaintenanceClass[]>([]);
  const [jobs, setJobs] = useState<RegenerationJob[]>([]);
  const [now, setNow] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [course, setCourse] = useState("");
  const [search, setSearch] = useState("");
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [components, setComponents] = useState<Component[]>(["content", "glossary", "flashcards"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const previousJobStates = useRef<Map<string, string>>(new Map());

  const refresh = useCallback(async () => {
    setNow(Date.now());
    try {
      const [nextClasses, nextJobs] = await Promise.all([
        maintenanceRequest<MaintenanceClass[]>("/rag/classes"), maintenanceRequest<RegenerationJob[]>("/regeneration/jobs"),
      ]);
      setClasses(nextClasses);
      setJobs(nextJobs);
      if (nextJobs.some(job => ["complete", "failed"].includes(job.status) && ["pending", "running"].includes(previousJobStates.current.get(job.id) || ""))) {
        await onChanged();
      }
      previousJobStates.current = new Map(nextJobs.map(job => [job.id, job.status]));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cargar la lista."); }
  }, [onChanged]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh]);

  const activeIds = useMemo(() => new Set(jobs.filter(job => ["pending", "running"].includes(job.status)).flatMap(job => job.items.map(item => item.note_id))), [jobs]);
  const visible = classes.filter(item => (!course || item.course === course) && `${item.title} ${item.module}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const eligible = visible.filter(item => item.can_regenerate && !activeIds.has(item.id));
  const courses = Array.from(new Set(classes.map(item => item.course))).sort();
  const chosen = classes.filter(item => selected.has(item.id) && item.can_regenerate && !activeIds.has(item.id));

  const toggle = (id: string) => setSelected(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const start = async (withInstructions: boolean) => {
    const requested = withInstructions ? components : ["content", "glossary", "flashcards"];
    if (!chosen.length || !requested.length) return;
    if (!window.confirm(`¿Regenerar ${chosen.length} clase(s)? Se reemplazará: ${requested.map(key => componentLabels[key as Component]).join(", ")}. Se harán llamadas a los modelos configurados y puede haber costes de API.`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await maintenanceRequest<RegenerationJob>("/regeneration/jobs", jsonRequest({ note_ids: chosen.map(item => item.id), components: requested, instructions: withInstructions ? instructions : "" }));
      setSelected(new Set());
      setInstructionsOpen(false);
      setNotice("Trabajo creado. Puedes salir de esta pestaña y consultar su progreso al volver.");
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo iniciar la regeneración."); }
    finally { setBusy(false); }
  };

  return <section className="space-y-5">
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
      <div><h2 className="text-xl font-bold">Cursos y clases</h2><p className="mt-1 text-sm text-slate-400">Selecciona clases procesadas para volver a generar su nota o algunos componentes. Las clases se procesan en el orden del curso.</p></div>
      <div className="flex flex-wrap gap-3">
        <label className="text-sm">Curso<select value={course} onChange={event => setCourse(event.target.value)} className="ml-2 rounded-lg border border-slate-700 bg-slate-950 p-2 max-w-full"><option value="">Todos los cursos</option>{courses.map(name => <option key={name}>{name}</option>)}</select></label>
        <label className="flex items-center gap-2 text-sm"><Search className="h-4 w-4" /><input aria-label="Buscar clase o módulo" placeholder="Buscar clase o módulo" value={search} onChange={event => setSearch(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 p-2" /></label>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={eligible.length > 0 && eligible.every(item => selected.has(item.id))} onChange={event => setSelected(previous => { const next = new Set(previous); for (const item of eligible) { if (event.target.checked) next.add(item.id); else next.delete(item.id); } return next; })} /> Seleccionar clases visibles</label>
        <span className="text-indigo-300">{chosen.length} seleccionadas</span>
        <button onClick={() => setSelected(new Set())} className="text-slate-400 hover:text-white cursor-pointer">Limpiar selección</button>
      </div>
      {courses.filter(name => visible.some(item => item.course === name)).map(name => <div key={name} className="rounded-xl border border-slate-800 overflow-hidden">
        <h3 className="bg-slate-800/60 px-4 py-3 font-semibold">{name}</h3>
        {visible.filter(item => item.course === name).map(item => <label key={item.id} className="flex items-start gap-3 border-t border-slate-800 px-4 py-3 cursor-pointer">
          <input type="checkbox" className="mt-1" checked={selected.has(item.id) && !activeIds.has(item.id)} disabled={!item.can_regenerate || activeIds.has(item.id) || busy} onChange={() => toggle(item.id)} />
          <span className="flex-1 min-w-0"><span className="block text-sm">{item.title}</span><span className="block text-xs text-slate-500 mt-1">{item.module || "Sin módulo"}</span></span>
          <span className="text-xs text-slate-400">{activeIds.has(item.id) ? "Regeneración pendiente" : item.can_regenerate ? "Procesada" : "Sin procesar"}</span>
        </label>)}
      </div>)}
      {!visible.length && <p className="text-slate-500">No hay clases para estos filtros.</p>}
    </div>
    <div className="sticky bottom-24 z-20 rounded-xl border border-slate-700 bg-slate-900/95 p-4 backdrop-blur flex flex-wrap gap-3">
      <button disabled={busy || !chosen.length} onClick={() => void start(false)} className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"><RefreshCw className="h-4 w-4" />Regenerar completo ahora</button>
      <button disabled={busy || !chosen.length} onClick={() => setInstructionsOpen(value => !value)} className="flex items-center gap-2 rounded-lg border border-indigo-400/50 px-4 py-2 text-sm font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"><Sparkles className="h-4 w-4" />Regenerar con instrucciones adicionales</button>
      {instructionsOpen && <div className="w-full space-y-3 border-t border-slate-700 pt-4">
        <p className="text-sm text-slate-400">Elige qué reemplazar; los componentes desmarcados se conservarán.</p>
        <div className="flex flex-wrap gap-5">{(Object.keys(componentLabels) as Component[]).map(key => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={components.includes(key)} onChange={event => setComponents(previous => event.target.checked ? [...previous, key] : previous.filter(value => value !== key))} />{componentLabels[key]}</label>)}</div>
        <label className="block text-sm">Instrucciones adicionales<textarea value={instructions} onChange={event => setInstructions(event.target.value)} maxLength={12000} rows={4} placeholder="Por ejemplo: profundiza en los ejemplos de código y evita repetir las definiciones." className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 p-3" /></label>
        <button disabled={busy || !components.length || !instructions.trim()} onClick={() => void start(true)} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Iniciar regeneración con instrucciones</button>
      </div>}
    </div>
    {error && <p role="alert" className="rounded-xl bg-rose-950/50 p-4 text-rose-300">{error}</p>}
    {notice && <p role="status" className="text-emerald-300 text-sm">{notice}</p>}
    <div className="space-y-3"><div className="flex items-center justify-between"><h2 className="text-lg font-bold">Historial de regeneraciones</h2><button onClick={() => { void refresh(); void onChanged(); }} className="text-sm text-indigo-300 cursor-pointer">Actualizar clases</button></div>
      {jobs.map(job => <details key={job.id} open={["pending", "running", "failed"].includes(job.status)} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <summary className="cursor-pointer text-sm">{statusLabels[job.status]} · {job.items.filter(item => item.status === "complete").length}/{job.items.length} clases · {job.components.map(key => componentLabels[key]).join(", ")} · {new Date(job.created_at).toLocaleString()}</summary>
        {job.instructions && <p className="mt-3 text-sm text-slate-400 whitespace-pre-wrap">{job.instructions}</p>}
        <ul className="mt-3 space-y-3">{job.items.map(item => <li key={item.note_id} className="text-sm">
          <span className={item.status === "failed" ? "text-rose-300" : item.status === "complete" ? "text-emerald-300" : "text-slate-300"}>{statusLabels[item.status]} — {item.title}</span>
          {item.status === "running" && item.phase && <p role="status" className="mt-1 text-xs text-indigo-300">{phaseLabels[item.phase] || "Procesando"}{item.phase_started_at && now > 0 && ` · ${duration(Math.max(0, now - Date.parse(item.phase_started_at)))}`}{item.phase === "evidence" && item.metrics?.evidence_page && ` · Parte ${item.metrics.evidence_page}/${item.metrics.evidence_pages}`}</p>}
          {item.metrics && <div className="mt-1 text-xs text-slate-400 space-y-1">
            {item.metrics.evidence_cache_hit ? <p>Evidencia reutilizada: fuentes e historial sin cambios.</p> : item.metrics.evidence_calls !== undefined && <p>Comparación de evidencia: {item.metrics.evidence_calls} llamadas{item.metrics.evidence_claims !== undefined && ` · ${item.metrics.evidence_claims} afirmaciones`}{!!item.metrics.evidence_format_retries && ` · ${item.metrics.evidence_format_retries} ajustes de formato`}</p>}
            {item.metrics.stage_ms && <p>{Object.entries(item.metrics.stage_ms).map(([phase, milliseconds]) => `${phaseLabels[phase] || "Procesamiento"}: ${duration(milliseconds)}`).join(" · ")}</p>}
            {!!item.metrics.llm_requests?.length && <RequestProgress requests={item.metrics.llm_requests} running={item.status === "running"} now={now} />}
            {item.metrics.llm_calls !== undefined && <p>Modelos: {item.metrics.llm_calls} llamadas · Tokens de entrada: {item.metrics.input_tokens ?? "—"} · Tokens de salida: {item.metrics.output_tokens ?? "—"}</p>}
            {item.metrics.flashcards_generated !== undefined && <p>Flashcards nuevas: {item.metrics.flashcards_generated}{item.metrics.flashcards_requested !== undefined && ` (máximo solicitado: ${item.metrics.flashcards_requested})`}. Se prioriza contenido útil sin duplicados, no completar una cuota.</p>}
            {item.metrics.auxiliary_fallback && <p>Se utilizó otro modelo auxiliar disponible por demora o indisponibilidad del seleccionado.</p>}
            {!!item.metrics.retrieval?.unindexed_prior_notes && <p className="text-amber-300">Hay {item.metrics.retrieval.unindexed_prior_notes} clases anteriores sin afirmaciones indexadas. La comparación puede ser incompleta; revisa su índice RAG.</p>}
          </div>}
          {item.error && <p className="mt-1 text-xs text-rose-300 whitespace-pre-wrap">{item.error}</p>}
        </li>)}</ul>
      </details>)}
      {!jobs.length && <p className="text-sm text-slate-500">Todavía no hay regeneraciones.</p>}
    </div>
  </section>;
}
