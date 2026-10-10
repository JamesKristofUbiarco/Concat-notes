"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import {
  DndContext, DragEndEvent, PointerSensor, TouchSensor, KeyboardSensor, closestCenter, pointerWithin, useDroppable, useSensor, useSensors,
} from "@dnd-kit/core";
import { Minus, MoreHorizontal, GripVertical, Link2, Palette, Plus, Trash2, Unlink2, Upload, X } from "lucide-react";
import { API_BASE, blockText, NoteBlock, StructuredNote } from "../lib/structuredNotes";
import { SmartMarkdownEditor } from "./SmartMarkdownEditor";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { gridBlocks, gridLane as visualLane, gridPosition, insertGridAfter, reorderGrid, gridRow, sectionGridRows, splitGridRow, mergeGridRow, appendGridBlock, moveGridToRow } from "../lib/blockGrid";

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
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
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
  const selectedBlocks = useMemo(() => note.document.blocks.filter((item) => selected.has(item.id)), [note, selected]);
  const lassoRelations = useMemo(() => selectedBlocks.length === 1
    ? relationsByBlock.get(selectedBlocks[0].id) || []
    : selectedRelations, [relationsByBlock, selectedBlocks, selectedRelations]);
  const selectionHasLasso = lassoRelations.length > 0 && lassoRelations.every((item) => item.style?.connector);
  const lassoAvailable = selectedBlocks.length === 1 ? lassoRelations.length > 0 : selectedPairs.length > 0;
  const sectionOrders = note.document.sections.map((section) => section.order);
  const topSectionOrder = Math.min(0, ...sectionOrders) - 10;
  const bottomSectionOrder = Math.max(0, ...sectionOrders) + 10;


  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLassoEnabled(selectionHasLasso);
      const savedColor = lassoRelations.find((item) => item.style?.connector)?.style?.color;
      if (savedColor) setConnectorColor(savedColor);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [lassoRelations, selectionHasLasso]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = JSON.parse(window.localStorage.getItem("concat-notes-connector-colors") || "[]");
        if (Array.isArray(saved)) setColorUsage(Object.fromEntries([...new Set([...saved, ...DEFAULT_COLORS])].map((color) => [color, 0])));
        else if (saved && typeof saved === "object") setColorUsage({ ...Object.fromEntries(DEFAULT_COLORS.map((color) => [color, 0])), ...saved });
      } catch { /* La paleta predeterminada sigue disponible. */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const palette = useMemo(() => Object.entries(colorUsage).sort((a, b) => b[1] - a[1]).map(([color]) => color).slice(0, 8), [colorUsage]);

  const registerBlock = useCallback((id: string, element: HTMLElement | null) => {
    if (element) {
      blockRefs.current.set(id, element);
    } else blockRefs.current.delete(id);
  }, []);

  const updateLines = useCallback(() => {
    const board = boardRef.current;
    if (!board) return;
    const origin = board.getBoundingClientRect();
    setLines(note.document.relations.flatMap((relation) => {
      if (!relation.style?.connector) return [];
      const from = blockRefs.current.get(relation.from_block_id)?.getBoundingClientRect();
      const to = blockRefs.current.get(relation.to_block_id)?.getBoundingClientRect();
      if (!from || !to || !from.width || !to.width) return [];
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

  const addBlock = async (sectionId: string, lane: "left" | "right", row = "start") => {
    const sectionBlocks = note.document.blocks.filter((item) => item.section_id === sectionId);
    const laneBlocks = sectionBlocks.filter((item) => item.lane === lane);
    const readingOrder = Math.max(0, ...laneBlocks.map((item) => item.reading_order)) + 10;
    const insertion = appendGridBlock(note.document, sectionId, lane, row);
    await onApply([...insertion.operations, { op: "insert_block", target_id: sectionId, block: { type: "markdown", lane, reading_order: readingOrder, content: "", layout: { position_y: insertion.position, grid_row: row }, sources: [] } }], "Añadir bloque");
  };

  const addSummary = async (sectionId: string) => {
    const summaries = note.document.blocks.filter((item) => item.section_id === sectionId && item.type === "summary");
    const readingOrder = Math.max(0, ...note.document.blocks.filter((item) => item.section_id === sectionId).map((item) => item.reading_order)) + 10;
    await onApply([{ op: "insert_block", target_id: sectionId, block: { type: "summary", lane: "right", reading_order: readingOrder, content: "", layout: { position_y: Math.max(-10, ...summaries.map(gridPosition)) + 10 }, sources: [] } }], "Añadir resumen");
  };

  const addBlockAfter = async (source: NoteBlock) => {
    const lane = visualLane(source);
    const insertion = insertGridAfter(note.document.blocks, source);
    await onApply([...insertion.operations, { op: "insert_after", target_id: source.id, block: {
      type: lane === "summary" ? "summary" : "markdown", lane: source.lane,
      reading_order: source.reading_order + 1, content: "", layout: { position_y: insertion.position, grid_row: gridRow(source) }, sources: [],
    } }], lane === "summary" ? "Añadir resumen" : "Añadir bloque");
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
  };

  const rememberColor = (color: string) => {
    const nextUsage = { ...colorUsage, [color]: (colorUsage[color] || 0) + 1 };
    setColorUsage(nextUsage);
    window.localStorage.setItem("concat-notes-connector-colors", JSON.stringify(nextUsage));
  };

  const toggleLasso = async (enabled: boolean) => {
    setLassoEnabled(enabled);
    if (!lassoRelations.length) return;
    const operations = lassoRelations.map((relation) => ({ op: "change_relation", target_id: relation.id, value: { style: { ...relation.style, connector: enabled, color: connectorColor } } }));
    if (enabled) rememberColor(connectorColor);
    await onApply(operations, enabled ? "Mostrar lazo visual" : "Ocultar lazo visual");
  };

  const chooseColor = async (color: string) => {
    setConnectorColor(color);
    if (!lassoRelations.length || !lassoEnabled) return;
    rememberColor(color);
    await onApply(lassoRelations.map((relation) => ({ op: "change_relation", target_id: relation.id, value: { style: { ...relation.style, connector: true, color } } })), "Cambiar color del lazo");
  };

  const disconnect = async () => {
    const operations = note.document.relations.filter((item) => selected.has(item.from_block_id) && selected.has(item.to_block_id)).map((item) => ({ op: "delete_relation", target_id: item.id }));
    if (operations.length) await onApply(operations, "Eliminar relaciones seleccionadas");
  };

  const dragEnd = async ({ active, over }: DragEndEvent) => {
    if (!over || disabled) return;
    const moving = note.document.blocks.find(block => block.id === active.id);
    const target = note.document.blocks.find(block => block.id === over.id);
    const zone = over.data.current;
    if (!moving) return;
    const row = target ? gridRow(target) : zone?.row;
    if (typeof row !== "string") return;
    const operations = target && gridRow(moving) === row
      ? reorderGrid(note.document.blocks, String(active.id), String(over.id))
      : moveGridToRow(note.document, String(active.id), row, target?.id,
          Boolean(active.rect.current.translated && active.rect.current.translated.top + active.rect.current.translated.height / 2 > over.rect.top + over.rect.height / 2));
    if (operations.length) await onApply(operations, "Reordenar bloques");
  };

  return <DndContext sensors={sensors} collisionDetection={(args) => {
    const active = note.document.blocks.find((block) => block.id === args.active.id);
    const containers = args.droppableContainers.filter(container => {
      const target = note.document.blocks.find(block => block.id === container.id);
      if (target) return active && active.section_id === target.section_id && visualLane(active) === visualLane(target);
      const zone = container.data.current;
      return active && zone?.kind === "grid-lane" && active.section_id === zone.section && visualLane(active) === zone.lane;
    });
    const hits = pointerWithin({ ...args, droppableContainers: containers });
    if (hits.length) {
      const blockHits = hits.filter(hit => note.document.blocks.some(block => block.id === hit.id));
      return blockHits.length ? blockHits : hits;
    }
    return closestCenter({ ...args, droppableContainers: containers });
  }} onDragEnd={(event) => void dragEnd(event)}>
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-1 md:hidden"><button onClick={() => setMobileLane("left")} className={`rounded-md px-3 py-1.5 text-xs font-bold ${mobileLane === "left" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Pistas</button><button onClick={() => setMobileLane("right")} className={`rounded-md px-3 py-1.5 text-xs font-bold ${mobileLane === "right" ? "bg-indigo-500/20 text-indigo-300" : "text-slate-500"}`}>Desarrollo</button></div>
        <button disabled={disabled} onClick={() => void onApply([{ op: "insert_section", section: { title: "Nueva sección", order: topSectionOrder } }], "Añadir sección arriba")} className="ml-auto flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300"><Plus className="h-3.5 w-3.5" /> Sección</button>
      </div>

      {selected.size > 0 && <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 w-max max-w-[calc(100vw-2rem)] max-h-[35vh] overflow-y-auto flex flex-wrap items-center gap-3 rounded-xl border border-indigo-500/30 bg-slate-950/95 p-3 shadow-xl backdrop-blur">
        <span className="mr-auto text-xs text-slate-300">{selected.size === 1 ? "Selecciona un bloque de la otra columna" : `${selected.size} bloques seleccionados`}</span>
        <button disabled={disabled || selectedPairs.length === 0} onClick={() => void toggleRelationship()} className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold disabled:opacity-40 ${selectionIsRelated ? "border-indigo-500 bg-indigo-600 text-white" : "border-slate-700 bg-slate-900 text-slate-300"}`} aria-pressed={selectionIsRelated}>{selectionIsRelated ? <Link2 className="h-3.5 w-3.5" /> : <Unlink2 className="h-3.5 w-3.5" />} {selectionIsRelated ? "Desvincular bloques" : "Vincular bloques"}</button>
        <div className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 p-1.5">
          <button disabled={disabled || !lassoAvailable} onClick={() => void toggleLasso(!lassoEnabled)} title={selectedBlocks.length === 1 && !lassoRelations.length ? "Este bloque todavía no tiene vínculos" : undefined} className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-bold disabled:opacity-40 ${lassoEnabled ? "border-indigo-500 bg-indigo-600 text-white" : "border-slate-700 bg-slate-950 text-slate-300"}`} aria-pressed={lassoEnabled}><Palette className="h-3.5 w-3.5" /> Lazo</button>
          {lassoEnabled && <div className="flex items-center gap-1 border-l border-slate-700 pl-2">{palette.slice(0, 5).map((color) => <button key={color} onClick={() => void chooseColor(color)} className={`h-5 w-5 rounded-full border-2 ${connectorColor === color ? "border-white" : "border-transparent"}`} style={{ backgroundColor: color }} aria-label={`Usar color ${color}`} />)}
          <input type="color" value={connectorColor} onChange={(event) => void chooseColor(event.target.value)} className="h-6 w-6 cursor-pointer rounded border-0 bg-transparent p-0" title="Elegir otro color" aria-label="Elegir color del lazo" /></div>}
        </div>
        <button disabled={disabled || !selectedBlocks.length || selectedBlocks.some(block => visualLane(block) === "summary" || block.section_id !== selectedBlocks[0].section_id || gridRow(block) !== gridRow(selectedBlocks[0]))} onClick={() => { const first = selectedBlocks[0]; void onApply(splitGridRow(note.document, first.section_id, gridRow(first), window.crypto.randomUUID(), selected), "Colocar separador antes de la selección"); }} title="Las celdas seleccionadas y las siguientes de cada columna comenzarán en un grupo nuevo" className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:text-indigo-300 disabled:opacity-40"><Minus className="h-3.5 w-3.5" /> Separador antes</button>
        <button disabled={disabled} onClick={() => onSelectedChange([])} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-white" title="Cancelar selección" aria-label="Cancelar selección"><X className="h-3.5 w-3.5" /></button>
      </div>}

      <div ref={boardRef} className="relative">
        <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible" aria-hidden="true">{lines.map((line) => <path key={line.id} d={`M ${line.x1} ${line.y1} C ${line.x1 + 35} ${line.y1}, ${line.x2 - 35} ${line.y2}, ${line.x2} ${line.y2}`} fill="none" stroke={line.color} strokeWidth="3" strokeLinecap="round" opacity="0.9" />)}</svg>
        <div className="hidden grid-cols-3 border-b border-slate-800 bg-slate-900/80 md:grid"><div className="px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-indigo-400">Pistas / preguntas</div><div className="col-span-2 border-l border-slate-800 px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-cyan-400">Desarrollo</div></div>
        {[...note.document.sections].sort((a, b) => a.order - b.order).map((section) => {
          const blocks = note.document.blocks.filter((item) => item.section_id === section.id).sort((a, b) => a.reading_order - b.reading_order);
          return <section id={`section-${section.id}`} key={section.id} className="border-b border-slate-800/80 last:border-0">
            <div className="flex items-center gap-2 border-b border-slate-800/60 bg-slate-900/50 px-5 py-3"><input defaultValue={section.title} onBlur={(event) => { const value = event.target.value.trim(); if (value && value !== section.title) void onApply([{ op: "rename_section", target_id: section.id, value }], "Renombrar sección"); }} className="min-w-0 flex-1 bg-transparent text-sm font-bold text-slate-200 outline-none focus:text-indigo-200" />{note.document.sections.length > 1 && <button onClick={() => void onApply([{ op: "delete_section", target_id: section.id }], "Eliminar sección")} className="p-1 text-slate-700 hover:text-rose-400" title="Eliminar sección"><Trash2 className="h-3.5 w-3.5" /></button>}</div>
            {sectionGridRows(note.document, section.id).map((row, index) => <div key={row} data-grid-row={row}>
              {index > 0 && <div className="flex items-center gap-2 px-3 py-2"><div className="h-px flex-1 bg-slate-700/60" /><span className="text-[10px] text-slate-500">Separador de alineación</span><button aria-label="Eliminar separador de alineación" title="Unir con el grupo anterior, conservando las celdas" disabled={disabled} onClick={() => void onApply(mergeGridRow(note.document, section.id, row), "Eliminar separador de alineación")} className="rounded p-1 text-slate-500 hover:text-rose-300 disabled:opacity-40"><X className="h-3.5 w-3.5" /></button><div className="h-px flex-1 bg-slate-700/60" /></div>}
              <div className="grid min-h-36 items-start md:grid-cols-3">
              <Lane sectionId={section.id} rowId={row} lane="left" hidden={mobileLane !== "left"} blocks={blocks.filter((item) => visualLane(item) === "left" && gridRow(item) === row)} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addBlock(section.id, "left", row)} onAddAfter={addBlockAfter} onRegister={registerBlock} disabled={disabled} />
              <Lane sectionId={section.id} rowId={row} lane="right" hidden={mobileLane !== "right"} blocks={blocks.filter((item) => visualLane(item) === "right" && gridRow(item) === row)} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addBlock(section.id, "right", row)} onAddAfter={addBlockAfter} onRegister={registerBlock} disabled={disabled} />
            </div>

              <button disabled={disabled} onClick={() => void onApply(splitGridRow(note.document, section.id, row, window.crypto.randomUUID(), new Set()), "Añadir separador de alineación")} className="mx-auto mb-3 flex items-center gap-2 rounded px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-800/40 hover:text-indigo-300 disabled:opacity-40"><Minus className="h-3.5 w-3.5" /> Añadir separador de alineación</button>
            </div>)}
            <div className="border-t border-slate-800/70 p-3">
              {blocks.some((item) => item.type === "summary") && <><p className="mb-2 px-1 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-400">Resumen</p><Lane lane="summary" hidden={false} blocks={blocks.filter((item) => item.type === "summary")} selected={selected} relationsByBlock={relationsByBlock} onToggle={toggle} onApply={onApply} onAdd={() => void addSummary(section.id)} onAddAfter={addBlockAfter} onRegister={registerBlock} disabled={disabled} hideAdd /></>}
              <button onClick={() => void addSummary(section.id)} disabled={disabled} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-500 hover:bg-slate-800/40 hover:text-slate-300 disabled:opacity-30"><Plus className="h-4 w-4" /> Añadir resumen</button>
            </div>
          </section>;
        })}
      </div>
      <div className="flex justify-center py-5"><button disabled={disabled} onClick={() => void onApply([{ op: "insert_section", section: { title: "Nueva sección", order: bottomSectionOrder } }], "Añadir sección abajo")} className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 hover:border-slate-600 hover:text-white disabled:opacity-30"><Plus className="h-3.5 w-3.5" /> Sección</button></div>
    </div>
  </DndContext>;
}

function Lane({ sectionId, rowId = "start", lane, hidden, blocks, selected, relationsByBlock, onToggle, onApply, onAdd, onAddAfter, onRegister, disabled, hideAdd = false }: { sectionId?: string; rowId?: string; lane: "left" | "right" | "summary"; hidden: boolean; blocks: NoteBlock[]; selected: Set<string>; relationsByBlock: Map<string, StructuredNote["document"]["relations"]>; onToggle: (id: string) => void; onApply: Props["onApply"]; onAdd: () => void; onAddAfter: (block: NoteBlock) => Promise<void>; onRegister: (id: string, element: HTMLElement | null) => void; disabled: boolean; hideAdd?: boolean }) {
  const ordered = gridBlocks(blocks);
  const section = sectionId || blocks[0]?.section_id;
  const { setNodeRef, isOver } = useDroppable({ id: `grid-lane:${section}:${rowId}:${lane}`, disabled: disabled || lane === "summary" || !section, data: { kind: "grid-lane", section, row: rowId, lane } });
  return <div ref={setNodeRef} data-grid-lane={lane} className={`${hidden ? "hidden md:block" : "block"} min-w-0 md:self-stretch ${isOver ? "bg-indigo-500/10" : ""} ${lane === "right" ? "md:col-span-2 md:border-l md:border-slate-800" : ""} ${lane === "summary" ? "p-0" : "p-3"}`}>
    <SortableContext items={ordered.map((block) => block.id)} strategy={verticalListSortingStrategy}><div className="flex min-h-12 flex-col gap-2">{!ordered.length && lane !== "summary" && <span className="px-3 py-3 text-xs text-slate-600">Arrastra una celda aquí</span>}{ordered.map((block) => <DraggableBlock key={block.id} block={block} selected={selected.has(block.id)} relations={relationsByBlock.get(block.id) || []} onToggle={() => onToggle(block.id)} onApply={onApply} onAddAfter={() => onAddAfter(block)} onRegister={onRegister} disabled={disabled} />)}</div></SortableContext>
    {!hideAdd && <button onClick={onAdd} disabled={disabled} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-700 px-3 py-3 text-xs font-bold text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-30"><Plus className="h-4 w-4" /> Añadir bloque</button>}
  </div>;
}

function DraggableBlock({ block, selected, relations, onToggle, onApply, onAddAfter, onRegister, disabled }: { block: NoteBlock; selected: boolean; relations: StructuredNote["document"]["relations"]; onToggle: () => void; onApply: Props["onApply"]; onAddAfter: () => Promise<void>; onRegister: (id: string, element: HTMLElement | null) => void; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: block.id, disabled });
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState(blockText(block));
  const savedText = blockText(block);
  useEffect(() => {
    const timer = window.setTimeout(() => setDraft(savedText), 0);
    return () => window.clearTimeout(timer);
  }, [savedText]);
  const style = { transform: transform ? `translate3d(0, ${transform.y}px, 0)` : undefined, transition };
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
  return <article ref={setRefs} style={style} className={`group relative min-w-0 rounded-md ${menuOpen ? "z-40" : isDragging ? "z-30" : "z-20"} ${isDragging ? "bg-slate-900 opacity-70" : ""} ${selected ? "bg-indigo-500/10 ring-1 ring-indigo-400/60" : "hover:bg-slate-800/20"}`}>
    <div className={`flex items-center gap-1 px-1 pt-1 transition-opacity md:absolute md:-top-4 md:right-1 md:z-30 md:rounded-md md:bg-slate-950/95 ${menuOpen || selected ? "opacity-100" : "md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"}`}>
      <button ref={setActivatorNodeRef} {...attributes} {...listeners} disabled={disabled} style={{ touchAction: "none" }} className="cursor-grab rounded p-1 text-slate-500 hover:text-slate-200 focus-visible:outline-2 focus-visible:outline-indigo-400 active:cursor-grabbing" aria-label="Reordenar bloque" title="Arrastra para reordenar; con teclado, espacio y flechas"><GripVertical className="h-4 w-4" /></button>
      <button onClick={onToggle} disabled={disabled} aria-pressed={selected} className={`rounded p-1 ${selected ? "bg-indigo-500/30 text-indigo-300" : "text-slate-500 hover:text-indigo-300"}`} aria-label={selected ? "Deseleccionar bloque" : "Seleccionar bloque para vincular"} title="Seleccionar para vincular"><Link2 className="h-4 w-4" /></button>
      {relations.length > 0 && <span className="text-[10px] text-indigo-300" title={`${relations.length} vínculos`}>{relations.length}</span>}
      <button onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-label="Acciones del bloque" className="rounded p-1 text-slate-500 hover:text-slate-200"><MoreHorizontal className="h-4 w-4" /></button>
      {menuOpen && <><button onClick={() => setMenuOpen(false)} className="fixed inset-0 z-30 cursor-default" aria-label="Cerrar acciones del bloque" /><div className="absolute right-0 top-full z-40 mt-1 min-w-44 rounded-lg border border-slate-700 bg-slate-950 p-1 shadow-xl">
        <button onClick={() => { setMenuOpen(false); void onAddAfter(); }} disabled={disabled} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-xs text-slate-300 hover:bg-slate-800"><Plus className="h-4 w-4" /> Añadir bloque debajo</button>
        <label className={`flex items-center gap-2 rounded px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 ${disabled ? "opacity-40" : "cursor-pointer"}`}><Upload className="h-4 w-4" /> Adjuntar imagen<input type="file" disabled={disabled} accept="image/*" className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadImage(file); event.target.value = ""; }} /></label>
        <button disabled={disabled} onClick={() => { if (window.confirm("¿Eliminar este bloque y sus vínculos?")) { setMenuOpen(false); void onApply([{ op: "delete_block", target_id: block.id }], "Eliminar bloque"); } }} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-xs text-rose-400 hover:bg-rose-500/10"><Trash2 className="h-4 w-4" /> Eliminar bloque</button>
      </div></>}
    </div>
    {block.type === "image" && typeof block.asset?.url === "string" && <div className="relative mx-3 mt-3 aspect-video overflow-hidden rounded-lg border border-slate-800"><Image src={block.asset.url} alt={String(block.asset.alt || draft || "Imagen")} fill unoptimized className="object-contain" /></div>}
    <SmartMarkdownEditor value={draft} onChange={setDraft} onCommit={save} disabled={disabled} compact placeholder={block.type === "image" ? "Descripción o texto alternativo…" : block.lane === "left" ? "Escribe una pista o pregunta…" : "Desarrolla la explicación…"} />
  </article>;
}
