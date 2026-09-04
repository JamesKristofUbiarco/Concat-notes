"use client";

import { useEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";
import { marked, type Tokens } from "marked";
import markedKatex from "marked-katex-extension";
import mermaid from "mermaid";

const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character] || character));

const renderer = {
  code({ text = "", lang = "" }: Tokens.Code) {
    return lang === "mermaid"
      ? `<div class="mermaid">${escapeHtml(text)}</div>`
      : `<pre><code class="language-${escapeHtml(lang)}">${escapeHtml(text)}</code></pre>`;
  },
  html({ text = "" }: Tokens.HTML | Tokens.Tag) { return escapeHtml(text); },
};
marked.use({ renderer }, markedKatex({ throwOnError: false, nonStandard: false }));

if (typeof window !== "undefined") {
  mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
}

export function MarkdownPreview({ markdown, className = "" }: { markdown: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(markdown || "") as string, {
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
  }), [markdown]);

  useEffect(() => {
    if (ref.current) void mermaid.run({ nodes: ref.current.querySelectorAll(".mermaid"), suppressErrors: true }).catch(() => undefined);
  }, [html]);

  return <article ref={ref} className={`markdown-preview ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
}
