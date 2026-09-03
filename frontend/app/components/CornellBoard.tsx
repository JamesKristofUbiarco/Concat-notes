"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import {
  DndContext, DragEndEvent, PointerSensor, useSensor, useSensors,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Braces, GripVertical, Link2, Plus, Trash2, Unlink2, Upload } from "lucide-react";
import { API_BASE, BlockType, blockText, NoteBlock, StructuredNote } from "../lib/structuredNotes";

const BLOCK_TYPES: Array<{ value: BlockType; label: string }> = [
  { value: "question", label: "Pregunta" }, { value: "concept", label: "Concepto" },
  { value: "paragraph", label: "Texto" }, { value: "heading", label: "Subtítulo" },
  { value: "bullet_list", label: "Lista" }, { value: "numbered_list", label: "Pasos" },
  { value: "code", label: "Código" }, { value: "command", label: "Comando" },
  { value: "code_output", label: "Salida" }, { value: "image", label: "Imagen" },
  { value: "warning", label: "Advertencia" }, { value: "callout", label: "Callout" },
  { value: "mermaid", label: "Mermaid" }, { value: "markdown", label: "Markdown" },
];

const RELATIONS = ["answers", "defines", "explains", "demonstrates", "produces", "warns_about", "references", "summarizes", "contrasts_with", "depends_on"];

interface Props {
  note: StructuredNote;
  selected: Set<string>;
  onSelectedChange: (ids: string[]) => void;
  onApply: (operations: unknown[], summary: string) => Promise<void>;
  disabled: boolean;
}

export function CornellBoard({ note, selected, onSelectedChange, onApply, disabled }: Props) {
  const [relationType, setRelationType] = useState("answers");
  const [mobileLane, setMobileLane] = useState<"left" | "right">("left");
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const relationsByBlock = useMemo(() => {
    const map = new Map<string, typeof note.document.relations>();
    for (const relation of note.document.relations) {
      for (const id of [relation.from_block_id, relation.to_block_id]) map.set(id, [...(map.get(id) || []), relation]);
    }
    return map;
  }, [note]);

  const toggle = (id: string) => onSelectedChange(selected.has(id) ? [...selected].filter((item) => item !== id) : [...selected, id]);

  const addBlock = async (sectionId: string, lane: "left" | "right") => {
    const anchor = note.document.blocks.filter((item) => item.section_id === sectionId).sort((a, b) => b.reading_order - a.reading_order)[0];
    if (!anchor) return;
    await onApply([{ op: "insert_after", target_id: anchor.id, block: { type: lane === "left" ? "question" : "paragraph", lane, content: "", layout: { gap_before: 0 }, sources: [] } }], "Añadir bloque");
  };

  const connect = async () => {
    const blocks = note.document.blocks.filter((item) => selected.has(item.id));
    const left = blocks.filter((item) => item.lane === "left");
    const right = blocks.filter((item) => item.lane === "right");
    if (!left.length || !right.length) return;
    const operations = left.flatMap((source) => right.map((target) => ({ op: "create_relation", relation: { from_block_id: source.id, to_block_id: target.id, type: relationType } })));
    await onApply(operations, `Relacionar bloques: ${relationType}`);
    onSelectedChange([]);
  };

  const disconnect = async () => {
    const operations = note.document.relations.filter((item) => selected.has(item.from_block_id) && selected.has(item.to_block_id)).map((item) => ({ op: "delete_relation", target_id: item.id }));
    if (operations.length) await onApply(operations, "Eliminar relaciones seleccionadas");
  };

  const dragEnd = async ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const moving = note.document.blocks.find((item) => item.id === active.id);
    const target = note.document.blocks.find((item) => item.id === over.id);
    if (!moving || !target) return;
    await onApply([{ op: "move_block", target_id: moving.id, value: { section_id: target.section_id, lane: target.lane, reading_order: target.reading_order } }], "Mover bloque");
  };

  return <DndContext sensors={sensors} onDragEnd={(event) => void dragEnd(event)}>
    <div className="mx-auto max-w-6xl">
      <div className="sticky top-20 z-20 mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/90 p-2.5 shadow-xl backdrop-blur">
        <div className="flex md:hidden rounded-lg border border-slate-800 bg-slate-900 p-1"><button onClick={() => setMobileLane("left")} className={`rounded-md px-3 py-1.5 text-xs font-bold ${mobileLane === "left" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Pistas</button><button onClick={() => setMobileLane("right")} className={`rounded-md px-3 py-1.5 text-xs font-bold ${mobileLane === "right" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Desarrollo</button></div>
        <span className="text-xs text-slate-500">{selected.size ? `${selected.size} bloques seleccionados` : "Selecciona bloques para relacionarlos"}</span>
        <div className="flex items-center gap-2"><select value={relationType} onChange={(event) => setRelationType(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-xs text-slate-300">{RELATIONS.map((item) => <option key={item}>{item}</option>)}</select><button disabled={disabled || selected.size < 2} onClick={() => void connect()} className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold disabled:opacity-40"><Link2 className="h-3.5 w-3.5" /> Relacionar</button><button disabled={disabled || selected.size < 2} onClick={() => void disconnect()} className="rounded-lg border border-slate-700 p-2 text-slate-400 disabled:opacity-40" title="Eliminar relaciones entre la selección"><Unlink2 className="h-3.5 w-3.5" /></button></div>
        <button disabled={disabled} onClick={() => void onApply([{ op: "insert_section", section: { title: "Nueva sección" } }], "Añadir sección")} className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300"><Plus className="h-3.5 w-3.5" /> Sección</button>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/35 shadow-2xl">
        <div className="hidden grid-cols-3 border-b border-slate-800 bg-slate-900/80 md:grid"><div className="px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-indigo-400">Pistas / preguntas</div><div className="col-span-2 border-l border-slate-800 px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-cyan-400">Desarrollo</div></div>
        {note.document.sections.sort((a, b) => a.order - b.order).map((section) => {
          const blocks = note.document.blocks.filter((item) => item.section_id === section.id).sort((a, b) => a.reading_order - b.reading_order);
          return <section id={`section-${section.id}`} key={section.id} className="border-b border-slate-800/80 last:border-0">
            <div className="flex items-center gap-2 border-b border-slate-800/60 bg-slate-900/50 px-5 py-3"><input defaultValue={section.title} onBlur={(event) => { const value = event.target.value.trim(); if (value && value !== section.title) void onApply([{ op: "rename_section", target_id: section.id, value }], "Renombrar sección"); }} className="min-w-0 flex-1 bg-transparent text-sm font-bold text-slate-200 outline-none focus:text-indigo-200" />{note.document.sections.length > 1 && <button onClick={() => void onApply([{ op: "delete_section", target_id: section.id }], "Eliminar sección")} className="p-1 text-slate-700 hover:text-rose-400" title="Eliminar sección"><Trash2 className="h-3.5 w-3.5" /></button>}</div>
            <SortableContext items={blocks.map((item) => item.id)} strategy={verticalListSortingStrategy}>
              <div className="grid min-h-36 md:grid-cols-3">
                <Lane lane="left" hidden={mobileLane !== "left"} blocks={blocks.filter((item) => item.lane === "left")} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addBlock(section.id, "left")} disabled={disabled} />
                <Lane lane="right" hidden={mobileLane !== "right"} blocks={blocks.filter((item) => item.lane === "right")} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addBlock(section.id, "right")} disabled={disabled} />
              </div>
            </SortableContext>
          </section>;
        })}
      </div>
    </div>
  </DndContext>;
}

function Lane({ lane, hidden, blocks, selected, relationsByBlock, onToggle, onApply, onAdd, disabled }: { lane: "left" | "right"; hidden: boolean; blocks: NoteBlock[]; selected: Set<string>; relationsByBlock: Map<string, StructuredNote["document"]["relations"]>; onToggle: (id: string) => void; onApply: Props["onApply"]; onAdd: () => void; disabled: boolean }) {
  return <div className={`${hidden ? "hidden md:block" : "block"} ${lane === "right" ? "md:col-span-2 md:border-l md:border-slate-800" : ""} p-3`}>
    <div className="space-y-2">{blocks.map((block) => <SortableBlock key={block.id} block={block} selected={selected.has(block.id)} relations={relationsByBlock.get(block.id) || []} onToggle={() => onToggle(block.id)} onApply={onApply} disabled={disabled} />)}</div>
    <button onClick={onAdd} disabled={disabled || blocks.length === 0} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-700 px-3 py-3 text-xs font-bold text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-30"><Plus className="h-4 w-4" /> Añadir bloque</button>
  </div>;
}

function SortableBlock({ block, selected, relations, onToggle, onApply, disabled }: { block: NoteBlock; selected: boolean; relations: StructuredNote["document"]["relations"]; onToggle: () => void; onApply: Props["onApply"]; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: block.id });
  const [draft, setDraft] = useState(blockText(block));
  const style = { transform: CSS.Transform.toString(transform), transition, marginTop: `${(block.layout?.gap_before || 0) * 4}px` };
  const save = async () => {
    if (draft === blockText(block)) return;
    await onApply([{ op: "replace_block", target_id: block.id, value: { ...block, content: draft } }], "Editar bloque");
  };
  const uploadImage = async (file: File) => {
    const form = new FormData(); form.append("file", file);
    const response = await fetch(`${API_BASE}/api/notes/images/upload`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo subir la imagen.");
    await onApply([{ op: "replace_block", target_id: block.id, value: { ...block, type: "image", content: draft, asset: { raw_note_image_id: data.id, filename: data.filename, url: data.image_url, alt: draft || data.filename } } }], "Añadir imagen");
  };
  return <article ref={setNodeRef} style={style} className={`group rounded-xl border bg-slate-950/75 transition ${isDragging ? "z-30 opacity-60" : ""} ${selected ? "border-indigo-400 ring-2 ring-indigo-500/20" : "border-slate-800 hover:border-slate-700"}`}>
    <div className="flex items-center gap-1 border-b border-slate-800/70 px-2 py-1.5">
      <button {...attributes} {...listeners} className="cursor-grab p-1 text-slate-600 hover:text-slate-300" aria-label="Mover bloque"><GripVertical className="h-3.5 w-3.5" /></button>
      <button onClick={onToggle} className={`h-4 w-4 rounded border ${selected ? "border-indigo-400 bg-indigo-500" : "border-slate-600"}`} aria-label="Seleccionar bloque" />
      <select value={block.type} onChange={(event) => void onApply([{ op: "change_block_type", target_id: block.id, value: event.target.value }], "Cambiar tipo de bloque")} className="min-w-0 flex-1 bg-transparent text-[10px] font-bold uppercase tracking-wide text-slate-500 outline-none">{BLOCK_TYPES.map((item) => <option key={item.value} value={item.value} className="bg-slate-900">{item.label}</option>)}</select>
      {relations.length > 0 && <span className="flex items-center gap-1 rounded-full bg-indigo-500/10 px-1.5 py-0.5 text-[9px] font-bold text-indigo-300"><Link2 className="h-2.5 w-2.5" />{relations.length}</span>}
      <button onClick={() => void onApply([{ op: "move_block", target_id: block.id, value: { layout: { ...block.layout, gap_before: Math.min(40, (block.layout?.gap_before || 0) + 2) } } }], "Aumentar separación")} className="p-1 text-slate-600 hover:text-slate-300" title="Aumentar separación"><Braces className="h-3 w-3" /></button>
      <button onClick={() => void onApply([{ op: "delete_block", target_id: block.id }], "Eliminar bloque")} className="p-1 text-slate-700 hover:text-rose-400" aria-label="Eliminar bloque"><Trash2 className="h-3.5 w-3.5" /></button>
    </div>
    {block.type === "image" && typeof block.asset?.url === "string" && <div className="relative mx-3 mt-3 aspect-video overflow-hidden rounded-lg border border-slate-800"><Image src={block.asset.url} alt={String(block.asset.alt || draft || "Imagen")} fill unoptimized className="object-contain" /></div>}
    <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onBlur={() => void save()} disabled={disabled} rows={Math.max(2, Math.min(14, draft.split("\n").length + Math.ceil(draft.length / 80)))} className={`w-full resize-none bg-transparent px-3 py-3 text-sm leading-relaxed outline-none ${block.type === "code" || block.type === "command" || block.type === "code_output" || block.type === "mermaid" ? "font-mono text-xs text-cyan-100" : "text-slate-200"}`} placeholder={block.type === "image" ? "Descripción o texto alternativo…" : block.lane === "left" ? "Escribe una pista o pregunta…" : "Desarrolla la explicación…"} />
    {block.type === "image" && <label className="mx-3 mb-3 flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 px-3 py-2 text-[10px] font-bold text-slate-500 hover:text-slate-300"><Upload className="h-3.5 w-3.5" /> {block.asset ? "Cambiar imagen" : "Subir imagen"}<input type="file" accept="image/*" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadImage(file); }} /></label>}
    {selected && relations.length > 0 && <div className="border-t border-indigo-500/20 bg-indigo-500/5 px-3 py-2 text-[10px] text-indigo-300">{relations.map((item) => item.type).join(" · ")}</div>}
  </article>;
}
