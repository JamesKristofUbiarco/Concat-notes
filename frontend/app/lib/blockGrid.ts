import type { NoteBlock, NoteDocumentData } from "./structuredNotes";

export function gridRow(block: NoteBlock): string {
  return typeof block.layout?.grid_row === "string" ? block.layout.grid_row : "start";
}

export function sectionGridRows(document: NoteDocumentData, section: string): string[] {
  const rows = (document.composition.grid_rows as Record<string, string[]> | undefined)?.[section];
  return ["start", ...(Array.isArray(rows) ? rows : [])];
}

export function gridLane(block: NoteBlock): "left" | "right" | "summary" {
  return block.type === "summary" ? "summary" : block.lane;
}

export function gridPosition(block: NoteBlock): number {
  const position = block.layout?.position_y;
  return typeof position === "number" && Number.isFinite(position)
    ? position : block.reading_order * 14.4;
}

export function gridBlocks(blocks: NoteBlock[]): NoteBlock[] {
  return [...blocks].sort((a, b) => gridPosition(a) - gridPosition(b) || a.reading_order - b.reading_order || a.id.localeCompare(b.id));
}

export function reorderGrid(blocks: NoteBlock[], activeId: string, overId: string) {
  const active = blocks.find((block) => block.id === activeId);
  const over = blocks.find((block) => block.id === overId);
  if (!active || !over || activeId === overId || active.section_id !== over.section_id || gridLane(active) !== gridLane(over) || gridRow(active) !== gridRow(over)) return [];
  const lane = gridBlocks(blocks.filter((block) => block.section_id === active.section_id && gridLane(block) === gridLane(active)));
  const group = lane.filter(block => gridRow(block) === gridRow(active));
  const from = group.findIndex((block) => block.id === activeId);
  const to = group.findIndex((block) => block.id === overId);
  group.splice(to, 0, group.splice(from, 1)[0]);
  let next = 0;
  const arranged = lane.map(block => gridRow(block) === gridRow(active) ? group[next++] : block);
  return arranged.map((block, index) => ({ op: "move_block", target_id: block.id, value: {
    layout: { ...block.layout, position_y: index * 10, alignment_group: null, pre_align_y: null, align_offset_px: 0 },
  } }));
}

export function splitGridRow(document: NoteDocumentData, section: string, row: string, nextId: string, selected: Set<string>) {
  const rows = sectionGridRows(document, section);
  const index = rows.indexOf(row);
  if (index < 0) return [];
  rows.splice(index + 1, 0, nextId);
  const operations: unknown[] = [{ op: "set_grid_rows", target_id: section, value: rows.slice(1) }];
  for (const lane of ["left", "right"] as const) {
    const blocks = gridBlocks(document.blocks.filter(b => b.section_id === section && gridLane(b) === lane && gridRow(b) === row));
    const anchor = blocks.findIndex(b => selected.has(b.id));
    if (anchor < 0) continue;
    operations.push(...blocks.slice(anchor).map(block => ({ op: "move_block", target_id: block.id, value: { layout: { ...block.layout, grid_row: nextId } } })));
  }
  return operations;
}

export function mergeGridRow(document: NoteDocumentData, section: string, row: string) {
  const rows = sectionGridRows(document, section);
  const index = rows.indexOf(row);
  if (index <= 0) return [];
  const previous = rows[index - 1];
  return [
    ...document.blocks.filter(b => b.section_id === section && gridRow(b) === row).map(block => ({ op: "move_block", target_id: block.id, value: { layout: { ...block.layout, grid_row: previous } } })),
    { op: "set_grid_rows", target_id: section, value: rows.filter(id => id !== row).slice(1) },
  ];
}

export function appendGridBlock(document: NoteDocumentData, section: string, lane: "left" | "right", row: string) {
  const rows = sectionGridRows(document, section);
  const blocks = gridBlocks(document.blocks.filter(b => b.section_id === section && gridLane(b) === lane))
    .sort((a, b) => rows.indexOf(gridRow(a)) - rows.indexOf(gridRow(b)));
  const following = blocks.findIndex(b => rows.indexOf(gridRow(b)) > rows.indexOf(row));
  const index = following < 0 ? blocks.length : following;
  return { position: index * 10, operations: blocks.map((block, ordinal) => ({ op: "move_block", target_id: block.id, value: { layout: { ...block.layout, position_y: (ordinal >= index ? ordinal + 1 : ordinal) * 10 } } })) };
}

export function moveGridToRow(document: NoteDocumentData, activeId: string, row: string, overId?: string, after = false) {
  const active = document.blocks.find(b => b.id === activeId);
  if (!active || gridLane(active) === "summary") return [];
  const rows = sectionGridRows(document, active.section_id);
  if (!rows.includes(row)) return [];
  const lane = gridBlocks(document.blocks.filter(b => b.section_id === active.section_id && gridLane(b) === gridLane(active)))
    .sort((a, b) => rows.indexOf(gridRow(a)) - rows.indexOf(gridRow(b)));
  const remaining = lane.filter(b => b.id !== activeId);
  const anchor = remaining.findIndex(b => b.id === overId && gridRow(b) === row);
  const nextGroup = remaining.findIndex(b => rows.indexOf(gridRow(b)) > rows.indexOf(row));
  const index = anchor >= 0 ? anchor + Number(after) : nextGroup < 0 ? remaining.length : nextGroup;
  remaining.splice(index, 0, { ...active, layout: { ...active.layout, grid_row: row } });
  if (remaining.every((b, i) => b.id === lane[i].id) && gridRow(active) === row) return [];
  return remaining.map((block, ordinal) => ({ op: "move_block", target_id: block.id, value: { layout: { ...block.layout, position_y: ordinal * 10 } } }));
}

// Make room after an anchor even when legacy blocks have identical coordinates.
export function insertGridAfter(blocks: NoteBlock[], source: NoteBlock) {
  const lane = gridBlocks(blocks.filter((block) => block.section_id === source.section_id && gridLane(block) === gridLane(source)));
  const index = lane.findIndex((block) => block.id === source.id);
  return {
    position: (index + 1) * 10,
    operations: lane.map((block, ordinal) => ({ op: "move_block", target_id: block.id, value: {
      layout: { ...block.layout, position_y: (ordinal > index ? ordinal + 1 : ordinal) * 10 },
    } })),
  };
}
