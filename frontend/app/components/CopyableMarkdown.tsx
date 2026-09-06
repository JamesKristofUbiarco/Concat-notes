"use client";

import { useState } from "react";
import { Copy, FileCode2 } from "lucide-react";
import { MarkdownPreview } from "./MarkdownPreview";

export function CopyableMarkdown({ markdown }: { markdown: string }) {
  const [formatted, setFormatted] = useState(true);
  const [message, setMessage] = useState("");

  const copy = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(markdown);
      } else {
        // También permite copiar al acceder por HTTP desde la red local.
        const previousFocus = document.activeElement as HTMLElement | null;
        const textarea = document.createElement("textarea");
        textarea.value = markdown;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        try {
          textarea.select();
          if (!document.execCommand("copy")) throw new Error("Clipboard unavailable");
        } finally {
          textarea.remove();
          previousFocus?.focus({ preventScroll: true });
        }
      }
      setMessage("Markdown copiado.");
    } catch {
      setMessage("No se pudo copiar. Puedes seleccionar el texto en la vista sin formato.");
    }
  };

  return <div className="mx-auto max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/60 p-6 md:p-10">
    <div className="mb-6 flex flex-wrap items-center gap-2 border-b border-slate-800 pb-4">
      <button onClick={() => void copy()} className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-indigo-400"><Copy className="h-4 w-4" /> Copiar Markdown</button>
      <button onClick={() => setFormatted((value) => !value)} aria-pressed={!formatted} className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-indigo-400"><FileCode2 className="h-4 w-4" /> {formatted ? "Ver sin formato" : "Ver formateado"}</button>
      <span role="status" className="text-xs text-slate-400">{message}</span>
    </div>
    {formatted ? <MarkdownPreview markdown={markdown} /> : <pre tabIndex={0} aria-label="Markdown sin formato" className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-sm leading-relaxed text-slate-300">{markdown}</pre>}
  </div>;
}
