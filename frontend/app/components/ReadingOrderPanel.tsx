"use client";

import { useState } from "react";
import { blockText, StructuredNote } from "../lib/structuredNotes";

export function ReadingOrderPanel({ note, onApply, onFocus, disabled }: {
  note: StructuredNote; onApply: (operations: unknown[], summary: string) => Promise<void>;
  onFocus: (id: string, next?: string) => void; disabled: boolean;
}) {
  const [dragged, setDragged] = useState<string | null>(null);
  const ids = note.reading_order_ids || note.document.blocks.map((b) => b.id);
  const move = async (from: string, to: string) => {
    const source = note.document.blocks.find((b) => b.id === from);
    const target = note.document.blocks.find((b) => b.id === to);
    if (!source || !target || source.section_id !== target.section_id || from === to) return;
    const group = source.layout?.alignment_group;
    const moving = ids.filter((id) => id === from || (group && note.document.blocks.find((b) => b.id === id)?.layout?.alignment_group === group));
    if (moving.includes(to)) return;
    const rest = ids.filter((id) => !moving.includes(id));
    const index = rest.indexOf(to);
    rest.splice(index, 0, ...moving);
    await onApply([{ op: "set_reading_order", value: rest }], "Ajustar recorrido de lectura");
  };
  return <div className="mb-4 rounded-xl border border-indigo-500/30 bg-slate-950 p-3">
    <p className="mb-2 text-xs text-slate-400">Arrastra para ajustar el recorrido dentro de una sección. Las parejas alineadas se mantienen juntas.</p>
    <button disabled={disabled} onClick={() => void onApply([{ op: "reset_reading_order" }], "Recuperar orden del tablero")} className="mb-3 text-xs text-indigo-300">Volver al orden del tablero</button>
    <ol className="max-h-64 space-y-2 overflow-y-auto">{ids.map((id, index) => {
      const block = note.document.blocks.find((b) => b.id === id);
      if (!block) return null;
      return <li key={id} draggable={!disabled} onDragStart={() => setDragged(id)} onDragEnd={() => setDragged(null)} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (dragged) void move(dragged, id); setDragged(null); }} className="flex items-center gap-2 rounded border border-slate-800 p-2 text-xs">
        <button onClick={() => onFocus(id, ids[index + 1])} className="min-w-0 flex-1 truncate text-left text-slate-300">{index + 1}. {blockText(block).slice(0, 90) || "Bloque vacío"}</button>
        <button aria-label="Subir en el recorrido" disabled={disabled || index === 0} onClick={() => void move(id, ids[index - 1])} className="px-2 text-indigo-300 disabled:opacity-30">↑</button>
        <input aria-label="Título para referencias Markdown" placeholder="Título de referencia" defaultValue={String(block.layout?.reading_label || "")} onBlur={(event) => { const title = event.target.value.trim(); if (title !== String(block.layout?.reading_label || "")) void onApply([{ op: "move_block", target_id: id, value: { layout: { ...block.layout, reading_label: title } } }], "Cambiar título de referencia"); }} disabled={disabled} className="w-32 rounded bg-slate-900 p-1 text-slate-300" />
      </li>;
    })}</ol>
  </div>;
}
