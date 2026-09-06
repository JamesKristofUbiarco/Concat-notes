export interface LayoutItem {
  id: string;
  lane: string;
  section: string;
  group?: unknown;
  top: number;
  height: number;
}

const GAP = 12;

// Alignment groups are indivisible rectangles, including when displaced.
export function arrangeDrag(items: LayoutItem[], activeId: string, delta: number): Map<string, number> {
  const result = new Map(items.map((item) => [item.id, item.top]));
  const active = items.find((item) => item.id === activeId);
  if (!active) return result;
  const section = items.filter((item) => item.section === active.section);
  const units: Array<{ items: LayoutItem[]; top: number; height: number; lanes: Set<string> }> = [];
  for (const item of section) {
    const existing = item.group ? units.find((unit) => unit.items[0].group === item.group) : undefined;
    if (existing) {
      existing.items.push(item);
      existing.top = Math.min(existing.top, item.top);
      existing.height = Math.max(...existing.items.map((entry) => entry.top + entry.height)) - existing.top;
      existing.lanes.add(item.lane);
    } else units.push({ items: [item], top: item.top, height: item.height, lanes: new Set([item.lane]) });
  }
  const moving = units.find((unit) => unit.items.some((item) => item.id === activeId))!;
  const target = Math.max(0, moving.top + delta);
  const remaining = units.filter((unit) => unit !== moving).sort((a, b) => a.top - b.top);
  // Every alignment group reserves the full strip in both columns, even when
  // all of its current members happen to live in the same column.
  const occupiedLanes = (unit: typeof moving) => unit.items.length > 1 ? new Set(["left", "right"]) : unit.lanes;
  const lanes = occupiedLanes(moving);
  const above = new Map<string, number>();
  const placed = new Map<typeof moving, number>();
  const below = new Map<string, number>([...lanes].map((lane) => [lane, target + moving.height + GAP]));
  const closed = new Set<string>();
  for (const unit of remaining) {
    const unitLanes = occupiedLanes(unit);
    const sharesStrip = [...unitLanes].some((lane) => lanes.has(lane));
    const earliest = Math.max(0, ...[...unitLanes].map((lane) => above.get(lane) || 0));
    const fitsAbove = ![...unitLanes].some((lane) => closed.has(lane))
      && (!sharesStrip || earliest + unit.height + GAP <= target)
      && (!sharesStrip || unit.top < target);
    let top: number;
    if (fitsAbove) {
      top = Math.max(earliest, sharesStrip ? Math.min(unit.top, target - unit.height - GAP) : unit.top);
      for (const lane of unitLanes) above.set(lane, top + unit.height + GAP);
    } else {
      top = Math.max(unit.top, earliest, ...[...unitLanes].map((lane) => below.get(lane) || 0));
      for (const lane of unitLanes) {
        closed.add(lane);
        below.set(lane, top + unit.height + GAP);
      }
    }
    placed.set(unit, top);
  }
  placed.set(moving, target);
  for (const [unit, top] of placed) {
    for (const item of unit.items) result.set(item.id, top + item.top - unit.top);
  }
  return result;
}
