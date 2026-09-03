"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ChevronLeft, Columns3, FileCode2, History, LoaderCircle, Menu,
  PanelRightClose, PanelRightOpen, Save, Undo2,
} from "lucide-react";
import { NavigationDock } from "../../components/NavigationDock";
import { CornellBoard } from "../../components/CornellBoard";
import { MarkdownPreview } from "../../components/MarkdownPreview";
import { AgentEditorPanel } from "../../components/AgentEditorPanel";
import { api, StructuredNote } from "../../lib/structuredNotes";

interface Revision {
  id: string;
  revision_number: number;
  change_kind: string;
  change_summary: string;
  actor: string;
  created_at: string;
}

export default function NoteEditorPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [note, setNote] = useState<StructuredNote | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [view, setView] = useState<"cornell" | "markdown">("cornell");
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [document, history] = await Promise.all([
        api<StructuredNote>(`/api/note-documents/${id}`),
        api<Revision[]>(`/api/note-documents/${id}/revisions`),
      ]);
      setNote(document);
      setRevisions(history);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo abrir la nota.");
    }
  }, [id]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  const applyOperations = useCallback(async (operations: unknown[], summary: string) => {
    if (!note || operations.length === 0) return;
    setBusy(true);
    try {
      const response = await api<{ document: StructuredNote }>(`/api/note-documents/${note.id}/operations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_revision_id: note.current_revision_id, operations, summary }),
      });
      setNote(response.document);
      setRevisions(await api<Revision[]>(`/api/note-documents/${id}/revisions`));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el cambio.");
      await load();
    } finally {
      setBusy(false);
    }
  }, [id, load, note]);

  const restore = async (revisionId: string) => {
    if (!note) return;
    setBusy(true);
    try {
      const response = await api<{ document: StructuredNote }>(`/api/note-documents/${note.id}/restore/${revisionId}`, { method: "POST" });
      setNote(response.document);
      setRevisions(await api<Revision[]>(`/api/note-documents/${id}/revisions`));
      setHistoryOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo restaurar la revisión.");
    } finally { setBusy(false); }
  };

  const selectedBlocks = useMemo(() => new Set(selected), [selected]);

  if (!note) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
      {error ? <div className="max-w-md rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-200">{error}</div> : <LoaderCircle className="h-8 w-8 animate-spin text-indigo-400" />}
    </div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 pb-24 text-slate-100">
      <header className="sticky top-0 z-40 flex min-h-16 items-center gap-3 border-b border-slate-800 bg-slate-950/95 px-3 backdrop-blur-xl md:px-5">
        <button onClick={() => router.back()} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white" aria-label="Volver"><ChevronLeft className="h-5 w-5" /></button>
        <button onClick={() => setOutlineOpen((value) => !value)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 md:hidden" aria-label="Abrir esquema"><Menu className="h-5 w-5" /></button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-400">{note.course_name || "Mis notas"}</p>
          <h1 className="truncate text-sm font-bold text-slate-100 md:text-base">{note.title}</h1>
        </div>
        <div className="hidden items-center gap-2 text-[11px] text-slate-500 md:flex"><Save className="h-3.5 w-3.5" /> Revisión {note.revision_number}{busy ? " · Guardando…" : " · Guardado"}</div>
        <div className="flex rounded-xl border border-slate-800 bg-slate-900 p-1">
          <button onClick={() => setView("cornell")} className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold ${view === "cornell" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}><Columns3 className="h-4 w-4" /><span className="hidden sm:inline">Cornell</span></button>
          <button onClick={() => setView("markdown")} className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold ${view === "markdown" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}><FileCode2 className="h-4 w-4" /><span className="hidden sm:inline">Markdown</span></button>
        </div>
        <button onClick={() => setHistoryOpen(true)} className="rounded-xl border border-slate-800 bg-slate-900 p-2.5 text-slate-400 hover:text-white" aria-label="Historial"><History className="h-4 w-4" /></button>
        <button onClick={() => setAssistantOpen((value) => !value)} className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-2.5 text-indigo-300" aria-label="Alternar asistente">{assistantOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}</button>
      </header>

      {error && <div className="mx-auto mt-4 max-w-3xl rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}

      <main className="flex min-h-[calc(100vh-4rem)]">
        <aside className={`${outlineOpen ? "fixed inset-y-16 left-0 z-30 flex w-72 md:static" : "hidden md:flex md:w-64"} shrink-0 flex-col border-r border-slate-800 bg-slate-950 p-4`}>
          <p className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">Esquema</p>
          <nav className="space-y-1">
            {note.document.sections.sort((a, b) => a.order - b.order).map((section) => (
              <a key={section.id} href={`#section-${section.id}`} onClick={() => setOutlineOpen(false)} className="block rounded-lg px-3 py-2 text-xs font-semibold text-slate-400 hover:bg-slate-900 hover:text-slate-100">{section.title}</a>
            ))}
          </nav>
          <div className="mt-auto rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-[11px] leading-relaxed text-slate-500">
            <p>{note.document.blocks.length} bloques · {note.document.relations.length} relaciones</p>
            <p className="mt-1">Los bloques no relacionados también son válidos.</p>
          </div>
        </aside>

        <section className="min-w-0 flex-1 overflow-x-hidden p-3 md:p-6">
          {view === "cornell" ? (
            <CornellBoard note={note} selected={selectedBlocks} onSelectedChange={setSelected} onApply={applyOperations} disabled={busy} />
          ) : (
            <div className="mx-auto max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/60 p-6 md:p-10"><MarkdownPreview markdown={note.rendered_markdown} /></div>
          )}
        </section>

        {assistantOpen && <AgentEditorPanel note={note} selectedBlockIds={selected} onApplied={(next) => { setNote(next); void load(); }} onClose={() => setAssistantOpen(false)} />}
      </main>

      <NavigationDock />

      {historyOpen && <div className="fixed inset-0 z-[70] flex justify-end bg-black/70" onMouseDown={() => setHistoryOpen(false)}><aside className="h-full w-full max-w-md overflow-y-auto border-l border-slate-800 bg-slate-950 p-5" onMouseDown={(event) => event.stopPropagation()}><div className="mb-5 flex items-center justify-between"><div><h2 className="font-bold">Historial</h2><p className="text-xs text-slate-500">Restaurar crea una revisión nueva.</p></div><button onClick={() => setHistoryOpen(false)} className="text-slate-400">×</button></div><div className="space-y-3">{revisions.map((revision) => <article key={revision.id} className={`rounded-xl border p-4 ${revision.id === note.current_revision_id ? "border-indigo-500/30 bg-indigo-500/10" : "border-slate-800 bg-slate-900/60"}`}><div className="flex items-center justify-between"><span className="text-xs font-bold">Revisión {revision.revision_number}</span><span className="text-[10px] uppercase text-slate-500">{revision.actor}</span></div><p className="mt-2 text-sm text-slate-300">{revision.change_summary}</p><p className="mt-2 text-[10px] text-slate-600">{new Date(revision.created_at).toLocaleString()}</p>{revision.id !== note.current_revision_id && <button onClick={() => void restore(revision.id)} className="mt-3 flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300"><Undo2 className="h-3.5 w-3.5" /> Restaurar</button>}</article>)}</div></aside></div>}
    </div>
  );
}
