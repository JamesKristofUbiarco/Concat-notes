"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Check, Copy, Menu, Paperclip, Pencil, Plus, Send, Square, Trash2, WandSparkles, X } from "lucide-react";
import Image from "next/image";
import { NavigationDock } from "../components/NavigationDock";
import { MarkdownPreview } from "../components/MarkdownPreview";
import { API_BASE, componentLabels, Component, jsonRequest, maintenanceRequest, MaintenanceClass } from "../lib/maintenanceApi";

interface Conversation { id: string; title: string; updated_at: string }
interface Attachment { id: string; url: string; filename: string }
interface Message { id: string; role: string; content: string; created_at: string; attachments: Attachment[] }
interface AgentRun { id: string; user_message_id: string; reply_message_id: string | null; status: string; progress: string; error: string | null; proposal_status: string | null; changes: { kind: string; label: string; diff: string; embedding_action: string | null }[] }
interface Detail extends Conversation { messages: Message[]; runs: AgentRun[]; has_more: boolean }
interface Model { id: string; name: string; configured: boolean }
const inputStyle = "rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400";

function ProposalView({ item, busy, onHandle }: { item: AgentRun; busy: boolean; onHandle: (item: AgentRun, action: "apply" | "reject") => Promise<void> }) {
  return <section className="mt-4 rounded-xl border border-violet-500/30 bg-violet-500/5 p-4 space-y-3">
    <h3 className="text-sm font-semibold">Propuesta de cambios · {item.changes.length} elementos</h3>
    {item.changes.map((change, index) => <details key={index} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3"><summary className="text-sm cursor-pointer break-words">{change.label}</summary>{change.embedding_action && <p className="mt-2 text-xs text-slate-400">{change.embedding_action === "delete_embedding" ? "Eliminar el vector semántico" : "Actualizar el embedding con VoyageAI"}</p>}<pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-300 font-mono">{change.diff || "Actualización del embedding; el texto se conserva."}</pre></details>)}
    {item.proposal_status === "pending" ? <div className="flex flex-wrap gap-3"><button disabled={busy} onClick={() => void onHandle(item, "apply")} className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold cursor-pointer disabled:opacity-40">Aplicar propuesta</button><button disabled={busy} onClick={() => void onHandle(item, "reject")} className="rounded-lg border border-slate-700 px-4 py-2 text-sm cursor-pointer disabled:opacity-40">Descartar</button></div> : <p className="text-xs text-slate-400">{item.proposal_status === "applied" ? "Propuesta aplicada" : "Propuesta descartada"}</p>}
  </section>;
}

export default function AgentPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [modelId, setModelId] = useState("");
  const [courses, setCourses] = useState<string[]>([]);
  const [course, setCourse] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [components, setComponents] = useState<Component[]>(["content", "glossary", "flashcards"]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [copyId, setCopyId] = useState<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const upload = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const activeId = useRef<string | null>(null);
  const requestSequence = useRef(0);
  const run = detail?.runs.find(item => ["pending", "running"].includes(item.status));

  const refreshHistory = useCallback(async () => setConversations(await maintenanceRequest<Conversation[]>("/agent/conversations")), []);
  const refreshChat = useCallback(async (id: string) => {
    const sequence = ++requestSequence.current;
    const next = await maintenanceRequest<Detail>(`/agent/conversations/${id}`);
    if (activeId.current === id && sequence === requestSequence.current) {
      // Conserva los mensajes antiguos ya cargados mientras se actualiza lo reciente.
      setDetail(previous => {
        const older = previous?.id === id ? previous.messages.filter(item => !next.messages.some(value => value.id === item.id) && item.created_at < (next.messages[0]?.created_at || "")) : [];
        return { ...next, messages: [...older, ...next.messages], runs: [...(previous?.id === id ? previous.runs.filter(item => !next.runs.some(value => value.id === item.id)) : []), ...next.runs], has_more: older.length ? previous!.has_more : next.has_more };
      });
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void Promise.all([refreshHistory(), maintenanceRequest<{ selected: string; options: Model[] }>("/agent/models"), maintenanceRequest<MaintenanceClass[]>("/rag/classes")]).then(([, catalog, classes]) => {
        setModels(catalog.options); setModelId(catalog.selected); setCourses(Array.from(new Set(classes.map(item => item.course))).sort());
        const stored = window.localStorage.getItem("agentConversationId");
        if (stored) { setCurrentId(stored); activeId.current = stored; }
      }).catch(reason => setError(reason instanceof Error ? reason.message : "No se pudo cargar el agente."));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshHistory]);

  useEffect(() => {
    activeId.current = currentId;
    if (!currentId) return;
    window.localStorage.setItem("agentConversationId", currentId);
    const initial = window.setTimeout(() => void refreshChat(currentId).catch(reason => setError(String(reason))), 0);
    const poll = window.setInterval(() => {
      void refreshChat(currentId).catch(reason => setError(String(reason)));
      void refreshHistory().catch(() => undefined);
    }, 1500);
    return () => { window.clearTimeout(initial); window.clearInterval(poll); };
  }, [currentId, refreshChat, refreshHistory]);

  useEffect(() => {
    const element = textarea.current;
    if (element) { element.style.height = "auto"; element.style.height = `${Math.min(element.scrollHeight, 200)}px`; }
  }, [draft]);
  const lastMessageId = detail?.messages.at(-1)?.id;
  useEffect(() => {
    if (stickToBottom.current && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [lastMessageId, run?.progress]);

  const switchConversation = (id: string | null) => {
    activeId.current = id; setCurrentId(id); setDetail(null); setSidebarOpen(false); setError(""); stickToBottom.current = true;
    if (!id) window.localStorage.removeItem("agentConversationId");
  };
  const newChat = async () => {
    try { const item = await maintenanceRequest<Conversation>("/agent/conversations", { method: "POST" }); switchConversation(item.id); await refreshHistory(); }
    catch (reason) { setError(String(reason)); }
  };
  const rename = async () => {
    if (!renameId || !renameTitle.trim()) return;
    try { await maintenanceRequest(`/agent/conversations/${renameId}`, { ...jsonRequest({ title: renameTitle }), method: "PATCH" }); setRenameId(null); await refreshHistory(); if (currentId === renameId) await refreshChat(renameId); }
    catch (reason) { setError(String(reason)); }
  };
  const remove = async (item: Conversation) => {
    if (!window.confirm(`¿Borrar la conversación «${item.title}» y sus propuestas? Los cambios que ya aplicaste en tus notas se conservarán.`)) return;
    try {
      const response = await fetch(`${API_BASE}/api/agent/conversations/${item.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("No se pudo borrar la conversación.");
      if (currentId === item.id) switchConversation(null);
      await refreshHistory();
    } catch (reason) { setError(String(reason)); }
  };
  const send = async (preset: "duplicates" | null = null) => {
    if (busy || uploading || run || !modelId || (preset === "duplicates" && !components.length)) return;
    const content = preset === "duplicates" ? `Revisa duplicados y repeticiones en ${components.map(key => componentLabels[key]).join(", ")}${course ? ` del curso «${course}»` : " de mis cursos"}. Propón sólo los cambios justificados y conserva la información útil.` : draft.trim() || (attachments.length ? "Analiza la imagen adjunta." : "");
    if (!content) return;
    setBusy(true); setError(""); stickToBottom.current = true;
    try {
      let id = currentId;
      if (!id) { const created = await maintenanceRequest<Conversation>("/agent/conversations", { method: "POST" }); id = created.id; activeId.current = id; setCurrentId(id); }
      await maintenanceRequest(`/agent/conversations/${id}/messages`, jsonRequest({ content, model_id: modelId, course: course || null, preset, components, image_ids: preset ? [] : attachments.map(item => item.id) }));
      if (!preset) { setDraft(""); setAttachments([]); }
      setDuplicateOpen(false);
      await Promise.all([refreshChat(id), refreshHistory()]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo enviar."); }
    finally { setBusy(false); textarea.current?.focus(); }
  };
  const cancel = async () => {
    if (!run || !currentId) return;
    setBusy(true); setError("");
    try { await maintenanceRequest(`/agent/runs/${run.id}/cancel`, { method: "POST" }); await refreshChat(currentId); }
    catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };
  const handleProposal = async (item: AgentRun, action: "apply" | "reject") => {
    if (action === "apply" && !window.confirm(`¿Aplicar los ${item.changes.length} cambios de esta propuesta? Revisa las diferencias: las eliminaciones pueden retirar tarjetas y sus repasos. Se actualizarán las notas y los índices afectados.`)) return;
    setBusy(true); setError("");
    try { await maintenanceRequest(`/agent/runs/${item.id}/${action}`, { method: "POST" }); if (currentId) await refreshChat(currentId); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo aplicar la propuesta."); }
    finally { setBusy(false); }
  };
  const attach = async (file: File) => {
    if (attachments.length >= 6) { setError("Puedes adjuntar hasta seis imágenes por mensaje."); return; }
    if (file.size > 10 * 1024 * 1024) { setError("La imagen debe pesar menos de 10 MB."); return; }
    setUploading(true); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      const response = await fetch(`${API_BASE}/api/notes/images/upload`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "No se pudo adjuntar la imagen.");
      setAttachments(previous => [...previous, { id: data.id, url: data.image_url, filename: data.filename }]);
    } catch (reason) { setError(String(reason)); }
    finally { setUploading(false); if (upload.current) upload.current.value = ""; }
  };
  const loadOlder = async () => {
    if (!currentId || !detail?.messages.length) return;
    try {
      const next = await maintenanceRequest<Detail>(`/agent/conversations/${currentId}?before=${detail.messages[0].id}`);
      const height = scroller.current?.scrollHeight || 0;
      setDetail(previous => previous ? { ...previous, messages: [...next.messages, ...previous.messages], runs: [...next.runs, ...previous.runs], has_more: next.has_more } : next);
      window.requestAnimationFrame(() => { if (scroller.current) scroller.current.scrollTop += scroller.current.scrollHeight - height; });
    } catch (reason) { setError(String(reason)); }
  };

  return <div className="h-dvh bg-slate-950 text-slate-100 px-3 md:px-6 pt-4 pb-24">
    <div className="mx-auto flex h-full max-w-7xl gap-4">
      {sidebarOpen && <button aria-label="Cerrar historial" className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={() => setSidebarOpen(false)} />}
      <aside className={`${sidebarOpen ? "fixed inset-y-0 left-0 z-40 flex" : "hidden"} md:relative md:flex w-72 shrink-0 flex-col rounded-2xl border border-slate-800 bg-slate-900 p-4 pb-24 md:pb-4`}>
        <div className="flex items-center justify-between"><h2 className="font-bold">Conversaciones</h2><button onClick={() => setSidebarOpen(false)} aria-label="Cerrar historial" className="md:hidden p-2 cursor-pointer"><X className="h-4 w-4" /></button></div>
        <button onClick={() => void newChat()} className="my-4 flex items-center justify-center gap-2 rounded-xl bg-violet-600 py-3 text-sm font-semibold cursor-pointer"><Plus className="h-4 w-4" />Nueva conversación</button>
        <input aria-label="Buscar conversación" placeholder="Buscar conversación" value={search} onChange={event => setSearch(event.target.value)} className={inputStyle} />
        <div className="mt-4 flex-1 overflow-y-auto space-y-2">
          {conversations.filter(item => item.title.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(item => <div key={item.id} className={`rounded-xl border p-3 ${currentId === item.id ? "border-violet-500/50 bg-violet-500/10" : "border-slate-800"}`}>
            {renameId === item.id ? <div className="space-y-2"><input autoFocus aria-label="Nombre de conversación" maxLength={255} value={renameTitle} onChange={event => setRenameTitle(event.target.value)} onKeyDown={event => { if (event.key === "Enter") void rename(); if (event.key === "Escape") setRenameId(null); }} className={`${inputStyle} w-full`} /><div className="flex gap-3 text-xs"><button onClick={() => void rename()} className="text-violet-300 cursor-pointer">Guardar</button><button onClick={() => setRenameId(null)} className="cursor-pointer">Cancelar</button></div></div> : <><button onClick={() => switchConversation(item.id)} className="block w-full text-left text-sm font-medium break-words cursor-pointer">{item.title}</button><div className="mt-2 flex justify-between items-center"><span className="text-[11px] text-slate-500">{new Date(item.updated_at).toLocaleDateString()}</span><div className="flex gap-2"><button aria-label={`Renombrar ${item.title}`} onClick={() => { setRenameId(item.id); setRenameTitle(item.title); }} className="p-1 text-slate-500 hover:text-violet-300 cursor-pointer"><Pencil className="h-3.5 w-3.5" /></button><button aria-label={`Borrar ${item.title}`} onClick={() => void remove(item)} className="p-1 text-slate-500 hover:text-rose-300 cursor-pointer"><Trash2 className="h-3.5 w-3.5" /></button></div></div></>}
          </div>)}
          {!conversations.length && <p className="text-sm text-slate-500">Aquí podrás continuar tus conversaciones.</p>}
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
        <header className="border-b border-slate-800 p-4 flex items-center gap-3"><button onClick={() => setSidebarOpen(true)} aria-label="Abrir historial" className="md:hidden p-2 cursor-pointer"><Menu className="h-5 w-5" /></button><Bot className="h-6 w-6 shrink-0 text-violet-400" /><div className="min-w-0"><h1 className="font-bold truncate">{detail?.title || "Agente"}</h1><p className="text-xs text-slate-500">Notas, memoria y aprendizaje</p></div></header>
        <div ref={scroller} onScroll={() => { if (scroller.current) stickToBottom.current = scroller.current.scrollHeight - scroller.current.scrollTop - scroller.current.clientHeight < 120; }} className="flex-1 min-h-0 overflow-y-auto p-4 md:p-6 space-y-5">
          {!detail?.messages.length && <div className="mx-auto max-w-lg py-8 text-center"><Bot className="mx-auto h-12 w-12 text-violet-400" /><h2 className="mt-4 text-xl font-semibold">Trabaja con tus notas</h2><p className="mt-3 text-sm leading-relaxed text-slate-400">Pídeme mejorar una explicación, revisar tu glosario, ajustar tarjetas, limpiar la memoria RAG o ayudarte a planear el estudio. Podrás revisar las modificaciones antes de aplicarlas.</p><div className="mt-5 flex flex-wrap justify-center gap-2">{["¿Cómo puedo organizar mi estudio?", "Busca notas que necesiten mejores ejemplos"].map(text => <button key={text} onClick={() => { setDraft(text); textarea.current?.focus(); }} className="rounded-xl border border-slate-700 p-3 text-xs text-slate-300 cursor-pointer">{text}</button>)}</div></div>}
          {detail?.has_more && <button onClick={() => void loadOlder()} className="block mx-auto text-sm text-violet-300 cursor-pointer">Cargar mensajes anteriores</button>}
          {detail?.messages.map(message => <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}><div className={`max-w-[95%] md:max-w-[88%] min-w-0 rounded-2xl p-4 ${message.role === "user" ? "bg-violet-500/15 border border-violet-500/20" : "bg-slate-900 border border-slate-800"}`}>
            <p className="mb-2 text-[11px] font-semibold text-slate-500">{message.role === "user" ? "Tú" : "Agente"}</p>
            <MarkdownPreview markdown={message.content} className="text-sm break-words [overflow-wrap:anywhere] [&_pre]:max-w-full [&_pre]:overflow-x-auto" />
            {message.attachments.map(image => <a key={image.id} href={image.url} target="_blank" rel="noreferrer" className="block mt-3"><Image unoptimized src={image.url} alt={image.filename} width={480} height={320} className="h-auto max-h-60 w-auto rounded-lg object-contain" /></a>)}
            <button aria-label="Copiar mensaje" onClick={() => { void navigator.clipboard.writeText(message.content).then(() => { setCopyId(message.id); window.setTimeout(() => setCopyId(null), 1500); }).catch(() => setError("No se pudo copiar el mensaje.")); }} className="mt-3 text-slate-500 hover:text-slate-200 cursor-pointer">{copyId === message.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}</button>
            {detail.runs.filter(item => item.user_message_id === message.id && ["failed", "cancelled"].includes(item.status)).map(item => <div key={item.id} className="mt-3 text-xs text-amber-300"><p>{item.error || "Envío cancelado"}</p><button disabled={busy || !!run} onClick={() => setDraft(message.content)} className="mt-2 underline cursor-pointer">Volver a preparar el mensaje</button></div>)}
            {detail.runs.filter(item => item.reply_message_id === message.id && item.changes.length > 0).map(item => <ProposalView key={item.id} item={item} busy={busy} onHandle={handleProposal} />)}
          </div></div>)}
          {run && <p role="status" className="flex items-center gap-2 text-sm text-violet-300"><span className="h-2 w-2 rounded-full bg-violet-400 animate-pulse" />{run.progress}…</p>}
        </div>
        <footer className="shrink-0 border-t border-slate-800 bg-slate-900 p-3 md:p-4 space-y-3">
          {error && <p role="alert" className="text-xs text-rose-300 whitespace-pre-wrap">{error}</p>}
          <div className="flex flex-wrap gap-2 items-center">
            <label className="flex-1 min-w-0"><span className="sr-only">Alcance de la conversación</span><select value={course} onChange={event => setCourse(event.target.value)} className={`${inputStyle} w-full max-w-full`}><option value="">Todos los cursos y mis notas</option>{courses.map(name => <option key={name}>{name}</option>)}</select></label>
            <button disabled={busy || !!run} onClick={() => setDuplicateOpen(value => !value)} className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs cursor-pointer disabled:opacity-40"><WandSparkles className="h-4 w-4" />Eliminación de duplicados</button>
          </div>
          {duplicateOpen && <div className="rounded-xl border border-slate-700 p-3 space-y-3"><p className="text-xs text-slate-400">Analizará las notas generadas del alcance seleccionado y preparará una propuesta. La revisión utiliza el modelo elegido.</p><div className="flex flex-wrap gap-4">{(Object.keys(componentLabels) as Component[]).map(key => <label key={key} className="flex gap-2 items-center text-xs"><input type="checkbox" checked={components.includes(key)} onChange={event => setComponents(previous => event.target.checked ? [...previous, key] : previous.filter(value => value !== key))} />{componentLabels[key]}</label>)}</div><button disabled={!components.length || busy || !!run} onClick={() => void send("duplicates")} className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold cursor-pointer disabled:opacity-40">Analizar duplicados</button></div>}
          {attachments.length > 0 && <div className="flex flex-wrap gap-2">{attachments.map(image => <div key={image.id} className="flex items-center gap-2 rounded-lg border border-slate-700 p-2 text-xs"><span className="max-w-40 truncate">{image.filename}</span><button aria-label={`Quitar ${image.filename}`} onClick={() => setAttachments(previous => previous.filter(item => item.id !== image.id))} className="cursor-pointer"><X className="h-3 w-3" /></button></div>)}</div>}
          <div className="rounded-xl border border-slate-700 focus-within:border-violet-400 bg-slate-950 p-2">
            <textarea ref={textarea} aria-label="Mensaje al agente" rows={2} maxLength={20000} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} placeholder="Escribe al agente…" className="block w-full min-h-12 max-h-[200px] resize-none overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] bg-transparent p-2 text-sm outline-none" />
            <div className="flex items-center justify-between gap-2 px-1 pb-1">
              <div className="flex items-center min-w-0 gap-2"><input ref={upload} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={event => { if (event.target.files?.[0]) void attach(event.target.files[0]); }} /><button disabled={uploading || busy} aria-label="Adjuntar imagen" title="Adjuntar imagen" onClick={() => upload.current?.click()} className="p-2 text-slate-400 hover:text-violet-300 cursor-pointer disabled:opacity-40"><Paperclip className="h-4 w-4" /></button><label className="min-w-0"><span className="sr-only">Modelo del agente</span><select aria-label="Modelo del agente" value={modelId} onChange={event => setModelId(event.target.value)} className="max-w-[180px] md:max-w-64 bg-slate-950 text-xs text-slate-400 outline-none rounded p-1">{models.map(option => <option key={option.id} value={option.id} disabled={!option.configured}>{option.name}{option.configured ? "" : " (sin API)"}</option>)}</select></label></div>
              <div className="flex gap-2">{run && <button disabled={busy} onClick={() => void cancel()} aria-label="Cancelar envío" title="Cancelar envío" className="rounded-lg border border-rose-500/50 p-2.5 text-rose-300 cursor-pointer disabled:opacity-40"><Square className="h-4 w-4" /></button>}<button disabled={busy || uploading || !!run || !modelId || (!draft.trim() && !attachments.length)} onClick={() => void send()} aria-label="Enviar mensaje" title="Enviar mensaje" className="rounded-lg bg-violet-600 p-2.5 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"><Send className="h-4 w-4" /></button></div>
            </div>
          </div>
          <p className="text-[10px] text-slate-500">Enter envía · Shift + Enter crea una línea{uploading ? " · Adjuntando imagen…" : ""}</p>
        </footer>
      </main>
    </div>
    <NavigationDock />
  </div>;
}
