"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, FilePenLine, FolderPlus, Menu, Pencil, Plus, Search, Tags, Trash2, X } from "lucide-react";
import { NavigationDock } from "../components/NavigationDock";
import { api, StructuredNote } from "../lib/structuredNotes";

interface Collection { id: string; name: string; description: string }
interface RawNote { id: string; course_name: string; class_title: string; course_module: string; status: string }

export default function MyNotesPage() {
  const [notes, setNotes] = useState<StructuredNote[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [classes, setClasses] = useState<RawNote[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [collectionOpen, setCollectionOpen] = useState(false);
  const [deletingNote, setDeletingNote] = useState<StructuredNote | null>(null);
  const [renamingNote, setRenamingNote] = useState<StructuredNote | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [documents, nextCollections, archive] = await Promise.all([
        api<StructuredNote[]>("/api/note-documents"),
        api<Collection[]>("/api/collections"),
        api<RawNote[]>("/api/notes/archive"),
      ]);
      setNotes(documents.filter((item) => item.origin_kind.startsWith("manual_")));
      setCollections(nextCollections); setClasses(archive); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudieron cargar tus notas."); }
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timer); }, [refresh]);

  const visible = useMemo(() => notes.filter((note) => {
    if (selectedCollection && note.collection_id !== selectedCollection) return false;
    const haystack = `${note.title} ${note.course_name} ${(note.tags || []).join(" ")}`.toLocaleLowerCase();
    return haystack.includes(query.toLocaleLowerCase());
  }), [notes, query, selectedCollection]);

  return <div className="min-h-screen bg-slate-950 px-4 pb-28 pt-8 text-slate-100 md:px-8">
    <div className="mx-auto max-w-7xl">
      <header className="mb-8 flex flex-col justify-between gap-4 border-b border-slate-800 pb-6 md:flex-row md:items-center"><div className="flex items-center gap-3"><button onClick={() => setSidebarOpen(true)} className="rounded-xl border border-slate-800 bg-slate-900 p-3 text-indigo-300 lg:hidden"><Menu className="h-5 w-5" /></button><span className="rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 p-3"><FilePenLine className="h-7 w-7" /></span><div><h1 className="text-2xl font-extrabold tracking-tight md:text-3xl">Mis notas</h1><p className="mt-1 text-sm text-slate-400">Escritura Cornell propia, conectada con tus clases y tu sistema de estudio.</p></div></div><button onClick={() => setCreateOpen(true)} className="flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-xs font-bold shadow-lg shadow-indigo-950"><Plus className="h-4 w-4" /> Nueva nota</button></header>
      {error && <div className="mb-5 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      <div className="flex gap-6">
        <aside className={`${sidebarOpen ? "fixed inset-0 z-50 flex w-72" : "hidden"} lg:static lg:flex lg:w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-950 pr-5`}><div className="mb-4 flex items-center justify-between lg:hidden"><span className="font-bold">Organización</span><button onClick={() => setSidebarOpen(false)}><X /></button></div><button onClick={() => { setSelectedCollection(null); setSidebarOpen(false); }} className={`mb-1 rounded-lg px-3 py-2 text-left text-xs font-bold ${!selectedCollection ? "bg-indigo-500/15 text-indigo-300" : "text-slate-400 hover:bg-slate-900"}`}>Todas las notas</button><p className="mb-2 mt-5 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-600">Colecciones</p>{collections.map((collection) => <button key={collection.id} onClick={() => { setSelectedCollection(collection.id); setSidebarOpen(false); }} className={`mb-1 rounded-lg px-3 py-2 text-left text-xs font-semibold ${selectedCollection === collection.id ? "bg-indigo-500/15 text-indigo-300" : "text-slate-400 hover:bg-slate-900"}`}>{collection.name}</button>)}<button onClick={() => setCollectionOpen(true)} className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold text-slate-500 hover:text-slate-300"><FolderPlus className="h-4 w-4" /> Nueva colección</button><div className="mt-8 space-y-2 rounded-xl border border-slate-800 bg-slate-900/50 p-3 text-[11px] text-slate-500"><p className="flex items-center gap-2"><BookOpen className="h-3.5 w-3.5" /> {notes.filter((item) => item.origin_kind === "manual_class_companion").length} vinculadas a clases</p><p className="flex items-center gap-2"><Tags className="h-3.5 w-3.5" /> {new Set(notes.flatMap((item) => item.tags || [])).size} etiquetas</p></div></aside>
        <main className="min-w-0 flex-1"><div className="mb-5 flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/60 px-4"><Search className="h-4 w-4 text-slate-600" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por título, curso o etiqueta…" className="w-full bg-transparent py-3 text-sm text-slate-200 outline-none" /></div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{visible.map((note) => <article key={note.id} className="group relative rounded-2xl border border-slate-800 bg-slate-900/55 transition hover:-translate-y-0.5 hover:border-indigo-500/40 hover:bg-slate-900"><Link href={`/editor/${note.id}`} className="block p-5"><div className="mb-5 flex items-center justify-between pr-16"><span className={`rounded-full px-2.5 py-1 text-[9px] font-black uppercase tracking-wider ${note.origin_kind === "manual_class_companion" ? "bg-cyan-500/10 text-cyan-300" : "bg-indigo-500/10 text-indigo-300"}`}>{note.origin_kind === "manual_class_companion" ? "Complementaria" : "Independiente"}</span><span className="text-[10px] text-slate-600">rev. {note.revision_number}</span></div><h2 className="line-clamp-2 text-base font-bold text-slate-100 group-hover:text-indigo-200">{note.title}</h2>{note.course_name && <p className="mt-2 truncate text-xs text-slate-500">{note.course_name}</p>}<div className="mt-5 flex flex-wrap gap-1.5">{(note.tags || []).slice(0, 4).map((tag) => <span key={tag} className="rounded-md bg-slate-800 px-2 py-1 text-[9px] text-slate-400">{tag}</span>)}</div><p className="mt-4 text-[10px] text-slate-600">Actualizada {new Date(note.updated_at).toLocaleDateString()}</p></Link><button onClick={() => setRenamingNote(note)} className="absolute right-12 top-3 rounded-lg p-2 text-slate-400 hover:bg-indigo-500/10 hover:text-indigo-300" title="Editar nombre" aria-label={`Editar nombre de ${note.title}`}><Pencil className="h-4 w-4" /></button><button onClick={() => setDeletingNote(note)} className="absolute right-3 top-3 rounded-lg border border-transparent p-2 text-slate-600 transition hover:border-rose-500/30 hover:bg-rose-500/10 hover:text-rose-300" title={`Eliminar ${note.title}`} aria-label={`Eliminar ${note.title}`}><Trash2 className="h-4 w-4" /></button></article>)}{visible.length === 0 && <button onClick={() => setCreateOpen(true)} className="col-span-full rounded-2xl border border-dashed border-slate-700 py-20 text-sm text-slate-500 hover:border-indigo-500/40 hover:text-indigo-300">Crea tu primera nota Cornell</button>}</div></main>
      </div>
    </div>
    <NavigationDock />
    {renamingNote && <RenameNoteModal note={renamingNote} onClose={() => setRenamingNote(null)} onRenamed={(updated) => { setNotes((items) => items.map((item) => item.id === updated.id ? updated : item)); setRenamingNote(null); }} />}
    {createOpen && <CreateNoteModal collections={collections} classes={classes} onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); void refresh(); }} />}
    {collectionOpen && <CollectionModal onClose={() => setCollectionOpen(false)} onCreated={() => { setCollectionOpen(false); void refresh(); }} />}
    {deletingNote && <DeleteNoteModal note={deletingNote} onClose={() => setDeletingNote(null)} onDeleted={() => { setNotes((items) => items.filter((item) => item.id !== deletingNote.id)); setDeletingNote(null); }} />}
  </div>;
}

function RenameNoteModal({ note, onClose, onRenamed }: { note: StructuredNote; onClose: () => void; onRenamed: (note: StructuredNote) => void }) {
  const [title, setTitle] = useState(note.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    if (busy || !title.trim()) return;
    setBusy(true); setError("");
    try {
      const response = await api<{ document: StructuredNote }>(`/api/note-documents/${note.id}/operations`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_revision_id: note.current_revision_id, operations: [{ op: "rename_note", value: title.trim() }], summary: "Cambiar título de la nota" }),
      });
      onRenamed(response.document);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cambiar el nombre."); }
    finally { setBusy(false); }
  };
  return <Modal title="Editar nombre de la nota" onClose={() => { if (!busy) onClose(); }}>
    <form onSubmit={(event) => { event.preventDefault(); void submit(); }} onKeyDown={(event) => { if (event.key === "Escape" && !busy) onClose(); }}>
      <Field label="Nombre"><input autoFocus value={title} maxLength={300} disabled={busy} onChange={(event) => setTitle(event.target.value)} className="input-editorial" /></Field>
      {error && <p role="alert" className="mt-3 text-xs text-rose-300">{error}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" disabled={busy} onClick={onClose} className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-bold">Cancelar</button>
        <button type="submit" disabled={busy || !title.trim()} className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold disabled:opacity-40">{busy ? "Guardando…" : "Guardar"}</button>
      </div>
    </form>
  </Modal>;
}

function CreateNoteModal({ collections, classes, onClose, onCreated }: { collections: Collection[]; classes: RawNote[]; onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState(""); const [collection, setCollection] = useState(""); const [linked, setLinked] = useState(""); const [tags, setTags] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const selectedClass = classes.find((item) => item.id === linked);
  const submit = async () => { setBusy(true); try { await api("/api/note-documents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, collection_id: collection || null, tags: tags.split(",").map((item) => item.trim()).filter(Boolean), linked_raw_note_id: linked || null, origin_kind: linked ? "manual_class_companion" : "manual_independent", course_name: selectedClass?.course_name || "", course_module: selectedClass?.course_module || "", class_title: selectedClass?.class_title || title }) }); onCreated(); } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo crear la nota."); } finally { setBusy(false); } };
  return <Modal title="Nueva nota" onClose={onClose}><div className="space-y-4"><Field label="Título"><input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus className="input-editorial" /></Field><Field label="Colección opcional"><select value={collection} onChange={(event) => setCollection(event.target.value)} className="input-editorial"><option value="">Sin colección</option>{collections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Complementar una clase"><select value={linked} onChange={(event) => setLinked(event.target.value)} className="input-editorial"><option value="">Nota independiente</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.course_name} — {item.class_title}</option>)}</select></Field><Field label="Etiquetas separadas por comas"><input value={tags} onChange={(event) => setTags(event.target.value)} className="input-editorial" /></Field>{error && <p className="text-xs text-rose-300">{error}</p>}<button disabled={busy || !title.trim()} onClick={() => void submit()} className="w-full rounded-xl bg-indigo-600 py-3 text-xs font-bold disabled:opacity-40">Crear y abrir después</button></div></Modal>;
}

function CollectionModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) { const [name, setName] = useState(""); const submit = async () => { await api("/api/collections", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }); onCreated(); }; return <Modal title="Nueva colección" onClose={onClose}><Field label="Nombre"><input value={name} onChange={(event) => setName(event.target.value)} autoFocus className="input-editorial" /></Field><button disabled={!name.trim()} onClick={() => void submit()} className="mt-4 w-full rounded-xl bg-indigo-600 py-3 text-xs font-bold disabled:opacity-40">Crear colección</button></Modal>; }
function DeleteNoteModal({ note, onClose, onDeleted }: { note: StructuredNote; onClose: () => void; onDeleted: () => void }) { const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const remove = async () => { setBusy(true); try { await api(`/api/note-documents/${note.id}`, { method: "DELETE" }); onDeleted(); } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo eliminar la nota."); setBusy(false); } }; return <Modal title="Eliminar nota" onClose={onClose}><p className="text-sm leading-relaxed text-slate-300">¿Quieres eliminar <strong className="text-white">{note.title}</strong>?</p><p className="mt-3 text-xs leading-relaxed text-slate-500">También se eliminarán sus revisiones, sesiones de edición y flashcards derivadas. Esta acción no elimina la clase vinculada.</p>{error && <p className="mt-3 text-xs text-rose-300">{error}</p>}<div className="mt-6 flex justify-end gap-2"><button disabled={busy} onClick={onClose} className="rounded-xl border border-slate-700 px-4 py-2.5 text-xs font-bold text-slate-300 disabled:opacity-40">Cancelar</button><button disabled={busy} onClick={() => void remove()} className="flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-40"><Trash2 className="h-4 w-4" />{busy ? "Eliminando…" : "Eliminar definitivamente"}</button></div></Modal>; }
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/75 p-4"><div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-950 p-5 shadow-2xl"><div className="mb-5 flex items-center justify-between"><h2 className="font-bold">{title}</h2><button onClick={onClose}><X className="h-4 w-4 text-slate-500" /></button></div>{children}</div></div>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block"><span className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-slate-500">{label}</span>{children}</label>; }
