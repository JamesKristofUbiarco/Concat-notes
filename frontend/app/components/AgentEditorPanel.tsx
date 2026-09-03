"use client";

import { useState } from "react";
import { Bot, Check, LoaderCircle, Send, Sparkles, X } from "lucide-react";
import { api, PatchProposal, StructuredNote } from "../lib/structuredNotes";

export function AgentEditorPanel({ note, selectedBlockIds, onApplied, onClose }: { note: StructuredNote; selectedBlockIds: string[]; onApplied: (note: StructuredNote) => void; onClose: () => void }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [scope, setScope] = useState<"selected_blocks" | "whole_note">("whole_note");
  const [proposal, setProposal] = useState<PatchProposal | null>(null);
  const [checked, setChecked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const session = await api<{ id: string }>(`/api/note-documents/${note.id}/edit-sessions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: "Edición con IA" }) });
    setSessionId(session.id);
    return session.id;
  };

  const send = async () => {
    if (!message.trim()) return;
    setBusy(true); setError("");
    try {
      const id = await ensureSession();
      const next = await api<PatchProposal>(`/api/note-edit-sessions/${id}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: message, scope, block_ids: selectedBlockIds }) });
      setProposal(next); setChecked(next.operations.map((_, index) => index)); setMessage("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "El agente no pudo proponer cambios."); }
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

  return <aside className="fixed inset-0 z-[60] flex w-full flex-col border-l border-slate-800 bg-slate-950 md:static md:z-auto md:w-[380px] md:shrink-0">
    <div className="flex items-center justify-between border-b border-slate-800 px-4 py-4"><div className="flex items-center gap-2"><span className="rounded-lg bg-indigo-500/15 p-2 text-indigo-300"><Bot className="h-4 w-4" /></span><div><h2 className="text-sm font-bold">Editor con IA</h2><p className="text-[10px] text-slate-500">Propone; tú decides qué aplicar.</p></div></div><button onClick={onClose} className="p-2 text-slate-500 hover:text-white"><X className="h-4 w-4" /></button></div>
    <div className="border-b border-slate-800 p-3"><div className="grid grid-cols-2 rounded-lg border border-slate-800 bg-slate-900 p-1"><button onClick={() => setScope("selected_blocks")} disabled={!selectedBlockIds.length} className={`rounded-md px-2 py-2 text-[10px] font-bold ${scope === "selected_blocks" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"} disabled:opacity-30`}>Selección ({selectedBlockIds.length})</button><button onClick={() => setScope("whole_note")} className={`rounded-md px-2 py-2 text-[10px] font-bold ${scope === "whole_note" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Toda la nota</button></div></div>
    <div className="flex-1 overflow-y-auto p-4">
      {!proposal && <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-xs leading-relaxed text-slate-400"><Sparkles className="mb-3 h-5 w-5 text-indigo-400" /><p>Pide una corrección, ampliación o reorganización concreta. La nota se preserva por defecto.</p></div>}
      {proposal && <div><div className="mb-4 rounded-xl border border-indigo-500/25 bg-indigo-500/10 p-4"><p className="text-[10px] font-black uppercase tracking-widest text-indigo-400">Intención interpretada</p><p className="mt-2 text-sm text-slate-200">{proposal.intent}</p><p className="mt-2 text-xs text-slate-400">{proposal.summary}</p></div><div className="space-y-2">{proposal.operations.map((operation, index) => <label key={index} className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${checked.includes(index) ? "border-emerald-500/30 bg-emerald-500/5" : "border-slate-800 bg-slate-900/50"}`}><input type="checkbox" checked={checked.includes(index)} onChange={() => setChecked((items) => items.includes(index) ? items.filter((item) => item !== index) : [...items, index])} className="mt-1" /><div className="min-w-0"><p className="text-xs font-bold text-slate-200">{operation.op}</p><p className="mt-1 truncate font-mono text-[9px] text-slate-600">{operation.target_id || "elemento nuevo"}</p><pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400">{JSON.stringify(operation.value ?? operation.block ?? operation.relation ?? "", null, 2)}</pre></div></label>)}</div></div>}
      {error && <div className="mt-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">{error}</div>}
    </div>
    <div className="border-t border-slate-800 p-3">{proposal && <div className="mb-3 flex gap-2"><button onClick={() => { setProposal(null); setChecked([]); }} className="flex-1 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-400">Descartar</button><button onClick={() => void apply()} disabled={busy || !checked.length} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold disabled:opacity-40"><Check className="h-3.5 w-3.5" /> Aplicar {checked.length}</button></div>}<div className="flex gap-2"><textarea value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} rows={3} placeholder={proposal ? "Pide ajustes a la propuesta…" : "Describe el cambio que necesitas…"} className="min-w-0 flex-1 resize-none rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500" /><button onClick={() => void send()} disabled={busy || !message.trim()} className="self-end rounded-xl bg-indigo-600 p-3 text-white disabled:opacity-40">{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button></div></div>
  </aside>;
}
