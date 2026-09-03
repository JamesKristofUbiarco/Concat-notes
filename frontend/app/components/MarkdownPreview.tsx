"use client";

import { useEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";
import { marked, type Tokens } from "marked";
import mermaid from "mermaid";

const renderer = {
  code({ text = "", lang = "" }: Tokens.Code) {
    return lang === "mermaid"
      ? `<div class="mermaid">${text}</div>`
      : `<pre><code class="language-${lang}">${text}</code></pre>`;
  },
};
marked.use({ renderer });

if (typeof window !== "undefined") {
  mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
}

export function MarkdownPreview({ markdown, className = "" }: { markdown: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(markdown || "") as string, {
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
  }), [markdown]);

  useEffect(() => {
    if (ref.current) void mermaid.run({ nodes: ref.current.querySelectorAll(".mermaid") });
  }, [html]);

  return <article ref={ref} className={`markdown-preview ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
}
