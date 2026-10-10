"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { Eye, Pencil, TriangleAlert } from "lucide-react";
import { MarkdownPreview } from "./MarkdownPreview";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onCommit: () => Promise<void> | void;
  disabled?: boolean;
  placeholder?: string;
  compact?: boolean;
}

const INDENT = "  ";

function containsSectionHeading(markdown: string) {
  let fence: string | null = null;
  for (const line of markdown.split("\n")) {
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (marker) {
      const token = marker[1];
      if (!fence) fence = token;
      else if (token[0] === fence[0] && token.length >= fence.length && !line.slice(marker[0].length).trim()) fence = null;
      continue;
    }
    if (!fence && /^ {0,3}# /.test(line)) return true;
  }
  return false;
}

export function SmartMarkdownEditor({ value, onChange, onCommit, disabled = false, placeholder = "Escribe Markdown…", compact = false }: Props) {
  const [editing, setEditing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const createsSection = containsSectionHeading(value);

  useEffect(() => {
    if (editing) textareaRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || !compact) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [value, editing, compact]);

  const setValueAndSelection = (next: string, start: number, end: number) => {
    onChange(next);
    window.requestAnimationFrame(() => textareaRef.current?.setSelectionRange(start, end));
  };

  const handleTab = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Tab") return;
    event.preventDefault();
    const textarea = event.currentTarget;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const selected = value.slice(lineStart, end);

    if (event.shiftKey) {
      const lines = selected.split("\n");
      let removedBeforeCursor = 0;
      const nextLines = lines.map((line, index) => {
        const removable = Math.min(INDENT.length, line.match(/^ */)?.[0].length || 0);
        if (index === 0) removedBeforeCursor = Math.min(removable, start - lineStart);
        return line.slice(removable);
      });
      const replacement = nextLines.join("\n");
      const next = value.slice(0, lineStart) + replacement + value.slice(end);
      const totalRemoved = selected.length - replacement.length;
      setValueAndSelection(next, Math.max(lineStart, start - removedBeforeCursor), Math.max(lineStart, end - totalRemoved));
      return;
    }

    if (selected.includes("\n")) {
      const replacement = selected.split("\n").map((line) => INDENT + line).join("\n");
      const next = value.slice(0, lineStart) + replacement + value.slice(end);
      setValueAndSelection(next, start + INDENT.length, end + INDENT.length * replacement.split("\n").length);
      return;
    }

    const next = value.slice(0, start) + INDENT + value.slice(end);
    setValueAndSelection(next, start + INDENT.length, start + INDENT.length);
  };

  if (!editing) {
    return <div role="button" tabIndex={disabled ? -1 : 0} onClick={() => { if (!disabled) setEditing(true); }} onKeyDown={(event) => { if (!disabled && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); setEditing(true); } }} className={`group/editor w-full cursor-text px-3 py-3 text-left ${compact ? "min-h-12" : "min-h-20"}`}>
      {value.trim() ? <MarkdownPreview markdown={value} className="smart-markdown-preview" /> : <span className="text-sm text-slate-600">{placeholder}</span>}
      {!compact && <span className="mt-2 hidden items-center gap-1 text-[10px] font-semibold text-slate-600 group-hover/editor:flex"><Pencil className="h-3 w-3" /> Editar Markdown</span>}
    </div>;
  }

  return <div className="divide-y divide-slate-800/70">
    {!compact && <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-indigo-300"><Pencil className="h-3 w-3" /> Markdown · Tab indenta · Shift+Tab desindenta</div>}
    <textarea
      ref={textareaRef}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        handleTab(event);
        if (event.key === "Escape") event.currentTarget.blur();
      }}
      onBlur={() => { setEditing(false); void onCommit(); }}
      disabled={disabled}
      rows={Math.max(3, Math.min(18, value.split("\n").length + Math.ceil(value.length / 75)))}
      aria-label={placeholder}
      className={`w-full px-3 py-3 font-mono text-sm leading-relaxed text-slate-200 outline-none placeholder:text-slate-700 ${compact ? "resize-none overflow-hidden bg-transparent" : "resize-y bg-slate-950/60"}`}
      placeholder={placeholder}
    />
    {createsSection && <div className="flex items-center gap-2 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-300"><TriangleAlert className="h-4 w-4 shrink-0" /> Se va a crear una nueva sección.</div>}
    {value.trim() && <div className={`${compact ? "bg-transparent" : "bg-slate-900/45"} px-3 py-3`}>{!compact && <div className="mb-2 flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest text-slate-600"><Eye className="h-3 w-3" /> Vista previa en vivo</div>}<MarkdownPreview markdown={value} className="smart-markdown-preview" /></div>}
  </div>;
}
