"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Bot, Check, LoaderCircle, Send, Sparkles, X } from "lucide-react";
import { api, PatchProposal, StructuredNote } from "../lib/structuredNotes";

interface ChatMessage { id: string; role: string; content: string; scope?: { proposal_id?: string; error?: boolean; image_ids?: string[] } }

export function AgentEditorPanel({ note, selectedBlockIds, onApplied, onClose, open = true }: { note: StructuredNote; selectedBlockIds: string[]; onApplied: (note: StructuredNote) => void; onClose: () => void; open?: boolean }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [scope, setScope] = useState<"selected_blocks" | "whole_note">("whole_note");
  const [proposal, setProposal] = useState<PatchProposal | null>(null);
  const [checked, setChecked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<Array<{ id: string; title: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<Array<{ id: string; name: string }>>([]);
  const [modelId, setModelId] = useState("");
  const [modelsOpen, setModelsOpen] = useState(false);
  const [attachments, setAttachments] = useState<Array<{ id: string; image_url: string; filename: string }>>([]);
  const [uploading, setUploading] = useState(false);
  const sending = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  const loadMessages = async (id: string) => {
    const history = await api<ChatMessage[]>(`/api/note-edit-sessions/${id}/messages`);
    setMessages(history);
    const proposalId = [...history].reverse().find((item) => item.scope?.proposal_id)?.scope?.proposal_id;
    if (proposalId && proposalId !== "None") {
      const saved = await api<PatchProposal>(`/api/note-patch-proposals/${proposalId}`);
      setProposal(saved.status === "validated" && saved.operations.length > 0 ? saved : null);
      setChecked(saved.operations.map((_, index) => index));
    } else setProposal(null);
  };

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      try {
        const available = await api<Array<{ id: string; name: string }>>("/api/note-editor/models");
        if (cancelled) return;
        setModels(available);
        const stored = window.localStorage.getItem("note-editor-model");
        setModelId(available.find((item) => item.id === stored)?.id || available[0]?.id || "");
        const saved = await api<Array<{ id: string; title: string }>>(`/api/note-documents/${note.id}/edit-sessions`);
        if (cancelled) return;
        setSessions(saved);
        if (saved.length) { setSessionId(saved[0].id); await loadMessages(saved[0].id); }
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "No se pudo cargar el historial."); }
      finally { if (!cancelled) setLoading(false); }
    };
    void restore();
    return () => { cancelled = true; };
  }, [note.id]);

  useEffect(() => { bottom.current?.scrollIntoView({ block: "nearest" }); }, [messages, busy, open]);

  const selectSession = async (id: string) => {
    setLoading(true); setError(""); setProposal(null); setMessages([]); setSessionId(id || null);
    try { if (id) await loadMessages(id); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cargar el historial."); }
    finally { setLoading(false); }
  };

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const session = await api<{ id: string }>(`/api/note-documents/${note.id}/edit-sessions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: "Edición con IA" }) });
    setSessionId(session.id);
    setSessions((items) => [{ id: session.id, title: "Edición con IA" }, ...items]);
    return session.id;
  };

  const send = async () => {
    if ((!message.trim() && !attachments.length) || !modelId || uploading || busy || sending.current || loading) return;
    sending.current = true;
    const content = message.trim() || "Analiza la imagen adjunta.";
    const imageIds = attachments.map((item) => item.id);
    setAttachments([]);
    setMessage("");
    setMessages((items) => [...items, { id: `pending-${Date.now()}`, role: "user", content, scope: { image_ids: imageIds } }]);
    setBusy(true); setError("");
    try {
      const id = await ensureSession();
      const next = await api<PatchProposal>(`/api/note-edit-sessions/${id}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, model_id: modelId, image_ids: imageIds, scope: selectedBlockIds.length ? scope : "whole_note", block_ids: selectedBlockIds }) });
      setProposal(next.operations.length ? next : null); setChecked(next.operations.map((_, index) => index));
      await loadMessages(id);
    } catch (reason) {
      const failure = reason instanceof Error ? reason.message : "El agente no pudo responder.";
      setError(failure);
      setMessages((items) => [...items, { id: `error-${Date.now()}`, role: "assistant", content: failure, scope: { error: true } }]);
    }
    finally { sending.current = false; setBusy(false); }
  };

  const upload = async (file: File) => {
    if (uploading || attachments.length >= 4) return;
    setUploading(true); setError("");
    try {
      const body = new FormData(); body.append("file", file);
      const image = await api<{ id: string; image_url: string; filename: string }>("/api/notes/images/upload", { method: "POST", body });
      setAttachments((items) => [...items, image]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo adjuntar la imagen."); }
    finally { setUploading(false); }
  };

  const reject = async () => {
    if (!proposal || busy) return;
    setBusy(true);
    try {
      await api(`/api/note-patch-proposals/${proposal.id}/reject`, { method: "POST" });
      setProposal(null); setChecked([]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo descartar la propuesta."); }
    finally { setBusy(false); }
  };

  const apply = async () => {
    if (!proposal || !checked.length) return;
    setBusy(true); setError("");
    try {
      const response = await api<{ document: StructuredNote }>(`/api/note-patch-proposals/${proposal.id}/apply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operation_indexes: checked }) });
      onApplied(response.document); setProposal(null); setChecked([]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo aplicar la propuesta."); }
    finally { setBusy(false); }
  };

  return <aside style={open ? undefined : { display: "none" }} className="fixed inset-0 z-[60] flex w-full flex-col border-l border-slate-800 bg-slate-950 min-h-0 overflow-hidden md:static md:z-auto md:w-[380px] md:shrink-0">
    <div className="flex items-center justify-between border-b border-slate-800 px-4 py-4"><div className="flex items-center gap-2"><span className="rounded-lg bg-indigo-500/15 p-2 text-indigo-300"><Bot className="h-4 w-4" /></span><div><h2 className="text-sm font-bold">Editor con IA</h2><p className="text-[10px] text-slate-500">Propone; tú decides qué aplicar.</p></div></div><button onClick={onClose} className="p-2 text-slate-500 hover:text-white"><X className="h-4 w-4" /></button></div>
    <div className="border-b border-slate-800 p-3"><div className="grid grid-cols-2 rounded-lg border border-slate-800 bg-slate-900 p-1"><button onClick={() => setScope("selected_blocks")} disabled={!selectedBlockIds.length} className={`rounded-md px-2 py-2 text-[10px] font-bold ${scope === "selected_blocks" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"} disabled:opacity-30`}>Selección ({selectedBlockIds.length})</button><button onClick={() => setScope("whole_note")} className={`rounded-md px-2 py-2 text-[10px] font-bold ${scope === "whole_note" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Toda la nota</button></div></div>
      <label className="shrink-0 block border-b border-slate-800 p-3 text-xs text-slate-400">Historial de conversaciones
        <select aria-label="Historial de conversaciones" disabled={busy || loading} value={sessionId || ""} onChange={(event) => void selectSession(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 p-2">
          <option value="">Nueva conversación</option>
          {sessions.map((item, index) => <option key={item.id} value={item.id}>{item.title} · {sessions.length - index}</option>)}
        </select>
      </label>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
      {loading && <p role="status" className="mb-3 text-xs text-slate-400">Cargando historial…</p>}
      <div role="log" aria-label="Conversación con el editor" aria-live="polite" className="mb-4 space-y-3">
        {messages.map((item) => <article key={item.id} className={`rounded-xl border p-3 text-sm ${item.role === "user" ? "ml-6 border-indigo-500/30 bg-indigo-500/10" : "mr-4 border-slate-800 bg-slate-900"}`}>
          <p className="mb-1 text-[10px] font-bold text-slate-400">{item.role === "user" ? "Tú" : "Editor con IA"}</p>
          <p className={`whitespace-pre-wrap break-words ${item.scope?.error ? "text-rose-300" : "text-slate-200"}`}>{item.content}</p>
          {!!item.scope?.image_ids?.length && <p className="mt-2 text-xs text-indigo-300">{item.scope.image_ids.length} imagen(es) adjunta(s)</p>}
        </article>)}
        {busy && <p role="status" className="flex items-center gap-2 text-xs text-indigo-300"><LoaderCircle className="h-4 w-4 animate-spin" /> Procesando…</p>}
      </div>
      {!proposal && <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-xs leading-relaxed text-slate-400"><Sparkles className="mb-3 h-5 w-5 text-indigo-400" /><p>Pide una corrección, ampliación o reorganización concreta. La nota se preserva por defecto.</p></div>}
      {proposal && <div><div className="mb-4 rounded-xl border border-indigo-500/25 bg-indigo-500/10 p-4"><p className="text-[10px] font-black uppercase tracking-widest text-indigo-400">Intención interpretada</p><p className="mt-2 text-sm text-slate-200">{proposal.intent}</p><p className="mt-2 text-xs text-slate-400">{proposal.summary}</p></div><div className="space-y-2">{proposal.operations.map((operation, index) => <label key={index} className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${checked.includes(index) ? "border-emerald-500/30 bg-emerald-500/5" : "border-slate-800 bg-slate-900/50"}`}><input type="checkbox" checked={checked.includes(index)} onChange={() => setChecked((items) => items.includes(index) ? items.filter((item) => item !== index) : [...items, index])} className="mt-1" /><div className="min-w-0"><p className="text-xs font-bold text-slate-200">{operation.op}</p><p className="mt-1 truncate font-mono text-[9px] text-slate-600">{operation.target_id || "elemento nuevo"}</p><pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400">{JSON.stringify(operation.value ?? operation.block ?? operation.relation ?? "", null, 2)}</pre></div></label>)}</div></div>}
      {error && <div className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">{error}</div>}
      <div ref={bottom} />
    </div>
    <div className="border-t border-slate-800 p-3">{proposal && <div className="mb-3 flex gap-2"><button disabled={busy} onClick={() => void reject()} className="flex-1 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-400">Descartar</button><button onClick={() => void apply()} disabled={busy || !checked.length} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold disabled:opacity-40"><Check className="h-3.5 w-3.5" /> Aplicar {checked.length}</button></div>}<div className="flex gap-2"><textarea aria-label="Mensaje al editor" value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} rows={3} placeholder={proposal ? "Pide ajustes a la propuesta…" : "Describe el cambio que necesitas…"} className="min-w-0 flex-1 resize-none rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500" /><button onClick={() => void send()} aria-label="Enviar mensaje" disabled={busy || loading || uploading || !modelId || (!message.trim() && !attachments.length)} className="self-end rounded-xl bg-indigo-600 p-3 text-white disabled:opacity-40">{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button></div></div>
    <div className="relative shrink-0 border-t border-slate-800 p-3">
      <div className="mb-2 flex flex-wrap gap-2">{attachments.map((item) => <div key={item.id} className="relative"><Image src={item.image_url} alt={item.filename} width={64} height={64} unoptimized className="h-16 w-16 rounded object-contain" /><button aria-label="Quitar imagen" onClick={() => setAttachments((items) => items.filter((image) => image.id !== item.id))} className="absolute right-0 top-0 rounded bg-slate-950 p-1"><X className="h-3 w-3" /></button></div>)}</div>
      <label className="mb-2 block text-xs text-indigo-300">{uploading ? "Subiendo imagen…" : "Adjuntar imagen"}<input aria-label="Adjuntar imagen" type="file" accept="image/png,image/jpeg,image/webp,image/gif" disabled={busy || uploading || attachments.length >= 4} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = ""; }} className="mt-1 block w-full text-xs" /></label>
      <button type="button" aria-expanded={modelsOpen} aria-controls="editor-model-list" disabled={busy || loading} onClick={() => setModelsOpen((value) => !value)} className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-left text-xs">{models.find((item) => item.id === modelId)?.name || "Sin modelos con visión disponibles"} · {modelsOpen ? "▾" : "▴"}</button>
      {modelsOpen && <div id="editor-model-list" onKeyDown={(event) => { if (event.key === "Escape") setModelsOpen(false); }} className="absolute bottom-14 left-3 right-3 z-20 max-h-60 overflow-y-auto rounded-xl border border-slate-700 bg-slate-950 p-2 shadow-xl">{models.map((item) => <button key={item.id} aria-pressed={item.id === modelId} onClick={() => { setModelId(item.id); window.localStorage.setItem("note-editor-model", item.id); setModelsOpen(false); }} className={`block w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-800 ${item.id === modelId ? "text-indigo-300" : "text-slate-300"}`}>{item.name}</button>)}</div>}
    </div>
  </aside>;
}
