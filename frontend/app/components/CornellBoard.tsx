"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import {
  DndContext, DragEndEvent, PointerSensor, useSensor, useSensors,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { AlignVerticalJustifyCenter, GripVertical, Link2, Palette, Plus, Trash2, Unlink2, Upload, X } from "lucide-react";
import { API_BASE, blockText, NoteBlock, StructuredNote } from "../lib/structuredNotes";

const DEFAULT_COLORS = ["#818cf8", "#22d3ee", "#34d399", "#fbbf24", "#fb7185"];

interface Props {
  note: StructuredNote;
  selected: Set<string>;
  onSelectedChange: (ids: string[]) => void;
  onApply: (operations: unknown[], summary: string) => Promise<void>;
  disabled: boolean;
}

export function CornellBoard({ note, selected, onSelectedChange, onApply, disabled }: Props) {
  const [mobileLane, setMobileLane] = useState<"left" | "right">("left");
  const [connectorColor, setConnectorColor] = useState(DEFAULT_COLORS[0]);
  const [lassoEnabled, setLassoEnabled] = useState(false);
  const [colorUsage, setColorUsage] = useState<Record<string, number>>(() => Object.fromEntries(DEFAULT_COLORS.map((color) => [color, 0])));
  const [lines, setLines] = useState<Array<{ id: string; x1: number; y1: number; x2: number; y2: number; color: string }>>([]);
  const boardRef = useRef<HTMLDivElement>(null);
  const blockRefs = useRef(new Map<string, HTMLElement>());
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const relationsByBlock = useMemo(() => {
    const map = new Map<string, typeof note.document.relations>();
    for (const relation of note.document.relations) {
      for (const id of [relation.from_block_id, relation.to_block_id]) map.set(id, [...(map.get(id) || []), relation]);
    }
    return map;
  }, [note]);
  const selectedPairs = useMemo(() => {
    const blocks = note.document.blocks.filter((item) => selected.has(item.id));
    const left = blocks.filter((item) => item.lane === "left");
    const right = blocks.filter((item) => item.lane === "right");
    return left.flatMap((source) => right.map((target) => ({ source, target })));
  }, [note, selected]);
  const selectedRelations = useMemo(() => selectedPairs.map(({ source, target }) => note.document.relations.find((item) => item.from_block_id === source.id && item.to_block_id === target.id)).filter((item): item is StructuredNote["document"]["relations"][number] => Boolean(item)), [note, selectedPairs]);
  const selectionIsRelated = selectedPairs.length > 0 && selectedRelations.length === selectedPairs.length;
  const selectionHasLasso = selectionIsRelated && selectedRelations.every((item) => item.style?.connector);

  useEffect(() => {
    setLassoEnabled(selectionHasLasso);
    const savedColor = selectedRelations.find((item) => item.style?.connector)?.style?.color;
    if (savedColor) setConnectorColor(savedColor);
  }, [selectionHasLasso, selectedRelations]);

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("concat-notes-connector-colors") || "[]");
      if (Array.isArray(saved)) setColorUsage(Object.fromEntries([...new Set([...saved, ...DEFAULT_COLORS])].map((color) => [color, 0])));
      else if (saved && typeof saved === "object") setColorUsage({ ...Object.fromEntries(DEFAULT_COLORS.map((color) => [color, 0])), ...saved });
    } catch { /* La paleta predeterminada sigue disponible. */ }
  }, []);

  const palette = useMemo(() => Object.entries(colorUsage).sort((a, b) => b[1] - a[1]).map(([color]) => color).slice(0, 8), [colorUsage]);

  const registerBlock = useCallback((id: string, element: HTMLElement | null) => {
    if (element) blockRefs.current.set(id, element);
    else blockRefs.current.delete(id);
  }, []);

  const updateLines = useCallback(() => {
    const board = boardRef.current;
    if (!board) return;
    const origin = board.getBoundingClientRect();
    setLines(note.document.relations.flatMap((relation) => {
      if (!relation.style?.connector) return [];
      const from = blockRefs.current.get(relation.from_block_id)?.getBoundingClientRect();
      const to = blockRefs.current.get(relation.to_block_id)?.getBoundingClientRect();
      if (!from || !to) return [];
      return [{ id: relation.id, x1: from.right - origin.left, y1: from.top + from.height / 2 - origin.top, x2: to.left - origin.left, y2: to.top + to.height / 2 - origin.top, color: relation.style.color || DEFAULT_COLORS[0] }];
    }));
  }, [note]);

  useLayoutEffect(() => {
    updateLines();
    const observer = new ResizeObserver(updateLines);
    if (boardRef.current) observer.observe(boardRef.current);
    for (const element of blockRefs.current.values()) observer.observe(element);
    window.addEventListener("resize", updateLines);
    return () => { observer.disconnect(); window.removeEventListener("resize", updateLines); };
  }, [updateLines]);

  const toggle = (id: string) => onSelectedChange(selected.has(id) ? [...selected].filter((item) => item !== id) : [...selected, id]);

  const addBlock = async (sectionId: string, lane: "left" | "right") => {
    const anchor = note.document.blocks.filter((item) => item.section_id === sectionId).sort((a, b) => b.reading_order - a.reading_order)[0];
    if (!anchor) return;
    await onApply([{ op: "insert_after", target_id: anchor.id, block: { type: "markdown", lane, content: "", layout: { gap_before: 0 }, sources: [] } }], "Añadir bloque");
  };

  const relationshipOperations = (withConnector = false) => {
    if (!selectedPairs.length) return [];
    return selectedPairs.map(({ source, target }) => {
      const existing = note.document.relations.find((item) => item.from_block_id === source.id && item.to_block_id === target.id);
      const semanticType = source.type === "concept" ? "defines" : source.type === "question" || source.type === "markdown" ? "answers" : "explains";
      if (existing) return withConnector ? { op: "change_relation", target_id: existing.id, value: { style: { ...existing.style, connector: true, color: connectorColor } } } : null;
      return { op: "create_relation", relation: {
        from_block_id: source.id,
        to_block_id: target.id,
        type: semanticType,
        style: withConnector ? { connector: true, color: connectorColor } : {},
      } };
    }).filter(Boolean);
  };

  const toggleRelationship = async () => {
    if (selectionIsRelated) {
      await disconnect();
      return;
    }
    const operations = relationshipOperations(lassoEnabled);
    if (!operations.length) return;
    if (lassoEnabled) rememberColor(connectorColor);
    await onApply(operations, "Relacionar bloques");
    onSelectedChange([]);
  };

  const rememberColor = (color: string) => {
    const nextUsage = { ...colorUsage, [color]: (colorUsage[color] || 0) + 1 };
    setColorUsage(nextUsage);
    window.localStorage.setItem("concat-notes-connector-colors", JSON.stringify(nextUsage));
  };

  const toggleLasso = async (enabled: boolean) => {
    setLassoEnabled(enabled);
    if (!selectionIsRelated) return;
    const operations = selectedRelations.map((relation) => ({ op: "change_relation", target_id: relation.id, value: { style: { ...relation.style, connector: enabled, color: connectorColor } } }));
    if (enabled) rememberColor(connectorColor);
    await onApply(operations, enabled ? "Mostrar lazo visual" : "Ocultar lazo visual");
  };

  const chooseColor = async (color: string) => {
    setConnectorColor(color);
    if (!selectionIsRelated || !lassoEnabled) return;
    rememberColor(color);
    await onApply(selectedRelations.map((relation) => ({ op: "change_relation", target_id: relation.id, value: { style: { ...relation.style, connector: true, color } } })), "Cambiar color del lazo");
  };

  const align = async () => {
    const elements = [...selected].map((id) => ({ id, element: blockRefs.current.get(id) })).filter((item): item is { id: string; element: HTMLElement } => Boolean(item.element));
    if (elements.length < 2) return;
    const targetTop = Math.max(...elements.map((item) => item.element.getBoundingClientRect().top));
    const operations = elements.map(({ id, element }) => {
      const block = note.document.blocks.find((item) => item.id === id)!;
      const currentOffset = Number(block.layout?.align_offset_px || 0);
      return { op: "move_block", target_id: id, value: { layout: { ...block.layout, align_offset_px: Math.max(0, Math.round(currentOffset + targetTop - element.getBoundingClientRect().top)) } } };
    });
    await onApply(operations, "Alinear bloques");
    onSelectedChange([]);
  };

  const disconnect = async () => {
    const operations = note.document.relations.filter((item) => selected.has(item.from_block_id) && selected.has(item.to_block_id)).map((item) => ({ op: "delete_relation", target_id: item.id }));
    if (operations.length) await onApply(operations, "Eliminar relaciones seleccionadas");
    onSelectedChange([]);
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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-1 md:hidden"><button onClick={() => setMobileLane("left")} className={`rounded-md px-3 py-1.5 text-xs font-bold ${mobileLane === "left" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Pistas</button><button onClick={() => setMobileLane("right")} className={`rounded-md px-3 py-1.5 text-xs font-bold ${mobileLane === "right" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Desarrollo</button></div>
        <button disabled={disabled} onClick={() => void onApply([{ op: "insert_section", section: { title: "Nueva sección" } }], "Añadir sección")} className="ml-auto flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300"><Plus className="h-3.5 w-3.5" /> Sección</button>
      </div>

      {selected.size > 0 && <div className="sticky top-20 z-20 mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-indigo-500/30 bg-slate-950/95 p-3 shadow-xl backdrop-blur">
        <span className="mr-auto text-xs text-slate-300">{selected.size === 1 ? "Selecciona un bloque de la otra columna" : `${selected.size} bloques seleccionados`}</span>
        <button disabled={disabled || selectedPairs.length === 0} onClick={() => void toggleRelationship()} className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold disabled:opacity-40 ${selectionIsRelated ? "border-indigo-500 bg-indigo-600 text-white" : "border-slate-700 bg-slate-900 text-slate-300"}`} aria-pressed={selectionIsRelated} title={selectionIsRelated ? "Quitar relación" : "Relacionar bloques"}>{selectionIsRelated ? <Link2 className="h-3.5 w-3.5" /> : <Unlink2 className="h-3.5 w-3.5" />} Relacionar</button>
        <div className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 p-1.5">
          <label className="flex cursor-pointer items-center gap-2 px-1 text-xs font-bold text-slate-300"><input type="checkbox" checked={lassoEnabled} disabled={disabled || selectedPairs.length === 0} onChange={(event) => void toggleLasso(event.target.checked)} className="accent-indigo-500" /><Palette className="h-3.5 w-3.5" /> Lazo</label>
          {lassoEnabled && <div className="flex items-center gap-1 border-l border-slate-700 pl-2">{palette.slice(0, 5).map((color) => <button key={color} onClick={() => void chooseColor(color)} className={`h-5 w-5 rounded-full border-2 ${connectorColor === color ? "border-white" : "border-transparent"}`} style={{ backgroundColor: color }} aria-label={`Usar color ${color}`} />)}
          <input type="color" value={connectorColor} onChange={(event) => void chooseColor(event.target.value)} className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent p-0" title="Elegir otro color" aria-label="Elegir color del lazo" /></div>}
        </div>
        <button disabled={disabled || selected.size < 2} onClick={() => void align()} className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 disabled:opacity-40" title="Colocar los bloques seleccionados a la misma altura"><AlignVerticalJustifyCenter className="h-3.5 w-3.5" /> Alinear</button>
        <button disabled={disabled} onClick={() => onSelectedChange([])} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-white" title="Cancelar selección" aria-label="Cancelar selección"><X className="h-3.5 w-3.5" /></button>
      </div>}

      <div ref={boardRef} className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/35 shadow-2xl">
        <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible" aria-hidden="true">{lines.map((line) => <path key={line.id} d={`M ${line.x1} ${line.y1} C ${line.x1 + 35} ${line.y1}, ${line.x2 - 35} ${line.y2}, ${line.x2} ${line.y2}`} fill="none" stroke={line.color} strokeWidth="3" strokeLinecap="round" opacity="0.9" />)}</svg>
        <div className="hidden grid-cols-3 border-b border-slate-800 bg-slate-900/80 md:grid"><div className="px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-indigo-400">Pistas / preguntas</div><div className="col-span-2 border-l border-slate-800 px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-cyan-400">Desarrollo</div></div>
        {note.document.sections.sort((a, b) => a.order - b.order).map((section) => {
          const blocks = note.document.blocks.filter((item) => item.section_id === section.id).sort((a, b) => a.reading_order - b.reading_order);
          return <section id={`section-${section.id}`} key={section.id} className="border-b border-slate-800/80 last:border-0">
            <div className="flex items-center gap-2 border-b border-slate-800/60 bg-slate-900/50 px-5 py-3"><input defaultValue={section.title} onBlur={(event) => { const value = event.target.value.trim(); if (value && value !== section.title) void onApply([{ op: "rename_section", target_id: section.id, value }], "Renombrar sección"); }} className="min-w-0 flex-1 bg-transparent text-sm font-bold text-slate-200 outline-none focus:text-indigo-200" />{note.document.sections.length > 1 && <button onClick={() => void onApply([{ op: "delete_section", target_id: section.id }], "Eliminar sección")} className="p-1 text-slate-700 hover:text-rose-400" title="Eliminar sección"><Trash2 className="h-3.5 w-3.5" /></button>}</div>
            <SortableContext items={blocks.map((item) => item.id)} strategy={verticalListSortingStrategy}>
              <div className="grid min-h-36 md:grid-cols-3">
                <Lane lane="left" hidden={mobileLane !== "left"} blocks={blocks.filter((item) => item.lane === "left")} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addBlock(section.id, "left")} onRegister={registerBlock} disabled={disabled} />
                <Lane lane="right" hidden={mobileLane !== "right"} blocks={blocks.filter((item) => item.lane === "right")} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addBlock(section.id, "right")} onRegister={registerBlock} disabled={disabled} />
              </div>
            </SortableContext>
          </section>;
        })}
      </div>
    </div>
  </DndContext>;
}

function Lane({ lane, hidden, blocks, selected, relationsByBlock, onToggle, onApply, onAdd, onRegister, disabled }: { lane: "left" | "right"; hidden: boolean; blocks: NoteBlock[]; selected: Set<string>; relationsByBlock: Map<string, StructuredNote["document"]["relations"]>; onToggle: (id: string) => void; onApply: Props["onApply"]; onAdd: () => void; onRegister: (id: string, element: HTMLElement | null) => void; disabled: boolean }) {
  return <div className={`${hidden ? "hidden md:block" : "block"} ${lane === "right" ? "md:col-span-2 md:border-l md:border-slate-800" : ""} p-3`}>
    <div className="space-y-2">{blocks.map((block) => <SortableBlock key={block.id} block={block} selected={selected.has(block.id)} relations={relationsByBlock.get(block.id) || []} onToggle={() => onToggle(block.id)} onApply={onApply} onRegister={onRegister} disabled={disabled} />)}</div>
    <button onClick={onAdd} disabled={disabled || blocks.length === 0} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-700 px-3 py-3 text-xs font-bold text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-30"><Plus className="h-4 w-4" /> Añadir bloque</button>
  </div>;
}

function SortableBlock({ block, selected, relations, onToggle, onApply, onRegister, disabled }: { block: NoteBlock; selected: boolean; relations: StructuredNote["document"]["relations"]; onToggle: () => void; onApply: Props["onApply"]; onRegister: (id: string, element: HTMLElement | null) => void; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: block.id });
  const [draft, setDraft] = useState(blockText(block));
  const style = { transform: CSS.Transform.toString(transform), transition, marginTop: `${Number(block.layout?.align_offset_px || 0)}px` };
  const setRefs = useCallback((element: HTMLElement | null) => { setNodeRef(element); onRegister(block.id, element); }, [block.id, onRegister, setNodeRef]);
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
  return <article ref={setRefs} style={style} className={`group relative z-20 rounded-xl border bg-slate-950/90 transition ${isDragging ? "z-30 opacity-60" : ""} ${selected ? "border-indigo-400 ring-2 ring-indigo-500/20" : "border-slate-800 hover:border-slate-700"}`}>
    <div className="flex items-center gap-1 border-b border-slate-800/70 px-2 py-1.5">
      <button {...attributes} {...listeners} className="cursor-grab p-1 text-slate-600 hover:text-slate-300" aria-label="Mover bloque"><GripVertical className="h-3.5 w-3.5" /></button>
      <button onClick={onToggle} className={`h-4 w-4 rounded border ${selected ? "border-indigo-400 bg-indigo-500" : "border-slate-600"}`} aria-label="Seleccionar bloque" />
      <span className="min-w-0 flex-1 px-1 text-[10px] font-bold uppercase tracking-wide text-slate-600">Markdown</span>
      {relations.length > 0 && <span className="flex items-center gap-1 rounded-full bg-indigo-500/10 px-1.5 py-0.5 text-[9px] font-bold text-indigo-300"><Link2 className="h-2.5 w-2.5" />{relations.length}</span>}
      <label className="cursor-pointer p-1 text-slate-600 hover:text-slate-300" title="Adjuntar imagen"><Upload className="h-3.5 w-3.5" /><input type="file" accept="image/*" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadImage(file); }} /></label>
      <button onClick={() => void onApply([{ op: "delete_block", target_id: block.id }], "Eliminar bloque")} className="p-1 text-slate-700 hover:text-rose-400" aria-label="Eliminar bloque"><Trash2 className="h-3.5 w-3.5" /></button>
    </div>
    {block.type === "image" && typeof block.asset?.url === "string" && <div className="relative mx-3 mt-3 aspect-video overflow-hidden rounded-lg border border-slate-800"><Image src={block.asset.url} alt={String(block.asset.alt || draft || "Imagen")} fill unoptimized className="object-contain" /></div>}
    <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onBlur={() => void save()} disabled={disabled} rows={Math.max(2, Math.min(14, draft.split("\n").length + Math.ceil(draft.length / 80)))} className={`w-full resize-none bg-transparent px-3 py-3 text-sm leading-relaxed outline-none ${block.type === "code" || block.type === "command" || block.type === "code_output" || block.type === "mermaid" ? "font-mono text-xs text-cyan-100" : "text-slate-200"}`} placeholder={block.type === "image" ? "Descripción o texto alternativo…" : block.lane === "left" ? "Escribe una pista o pregunta…" : "Desarrolla la explicación…"} />
    {selected && relations.length > 0 && <div className="border-t border-indigo-500/20 bg-indigo-500/5 px-3 py-2 text-[10px] text-indigo-300">Este bloque está relacionado con {relations.length === 1 ? "otro bloque" : `${relations.length} bloques`}.</div>}
  </article>;
}
