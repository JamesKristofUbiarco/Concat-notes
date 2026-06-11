import React from "react";
import { FileCode2, Copy, Check, AlertTriangle, Cpu, Activity } from "lucide-react";

interface ResultPanelProps {
  markdownResult: string;
  copyState: "idle" | "success" | "empty";
  onCopy: () => void;
  isAIProcessing: boolean;
  aiStep: number;
}

export function ResultPanel({ markdownResult, copyState, onCopy, isAIProcessing, aiStep }: ResultPanelProps) {
  const cleanMarkdown = (md: string) => {
    if (!md) return "";
    return md
      .replace(/^`{4,}(?:[a-zA-Z0-9_-]+)?\n?/, "") // Remove starting 4+ backticks + optional lang + newline
      .replace(/\n?`{4,}$/, ""); // Remove trailing newline + 4+ backticks
  };

  return (
    <section className="lg:col-span-5 flex flex-col bg-slate-900/80 rounded-2xl border border-slate-800 glassmorphism shadow-2xl relative overflow-hidden min-h-[500px]">
      
      {/* Cabecera del Resultado */}
      <div className="bg-slate-900 border-b border-slate-800/80 px-5 py-4 flex justify-between items-center">
        <span className="text-sm font-bold text-slate-200 flex items-center gap-2">
          <FileCode2 className="w-4.5 h-4.5 text-indigo-400" />
          Resultado Estructurado
        </span>
        
        {/* Botón de Copiar */}
        <button 
          type="button" 
          onClick={onCopy}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-300 border border-slate-850 cursor-pointer ${
            copyState === "success" 
              ? "bg-emerald-500/15 border-emerald-500/35 text-emerald-400" 
              : copyState === "empty"
              ? "bg-rose-500/15 border-rose-500/35 text-rose-400"
              : "bg-slate-950/70 hover:bg-slate-900 text-slate-300 hover:text-slate-100 hover:border-slate-700"
          }`}
        >
          {copyState === "success" ? (
            <>
              <Check className="w-3.5 h-3.5" />
              <span>¡Copiado!</span>
            </>
          ) : copyState === "empty" ? (
            <>
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>¡Vacío!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copiar texto</span>
            </>
          )}
        </button>
      </div>

      {/* AREA DE PROCESAMIENTO ACTIVO */}
      {isAIProcessing && (
        <div className="absolute inset-0 bg-slate-950/90 backdrop-blur-md z-20 flex flex-col items-center justify-center p-6 text-center animate-fade-in">
          <div className="relative mb-6">
            <div className="w-20 h-20 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center animate-pulse glow-indigo">
              <Cpu className="w-9 h-9 text-indigo-400 animate-spin" style={{ animationDuration: '6s' }} />
            </div>
            <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-indigo-400 to-transparent animate-scanning" />
          </div>

          <h3 className="text-lg font-bold text-slate-200 mb-2">Procesando Apuntes Crudos</h3>
          <p className="text-xs text-slate-400 max-w-sm mb-8 leading-relaxed">
            El agente LangGraph está estructurando semánticamente las notas y archivándolas automáticamente.
          </p>

          <div className="w-full max-w-xs flex flex-col gap-3.5 text-left border border-slate-800/80 bg-slate-900/60 rounded-xl p-4.5">
            {[
              { step: 1, label: "Contexto semántico (pgvector)..." },
              { step: 2, label: "Síntesis Markdown (Synapse Scholar)..." },
            ].map(({ step, label }) => (
              <div key={step} className="flex items-center gap-3">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                  aiStep > step ? "bg-emerald-500/20 text-emerald-400" : aiStep === step ? "bg-indigo-500 text-white animate-pulse" : "bg-slate-800 text-slate-500"
                }`}>
                  {aiStep > step ? "✓" : step}
                </div>
                <span className={`text-xs font-medium ${aiStep === step ? "text-indigo-300 font-semibold" : aiStep > step ? "text-slate-400" : "text-slate-600"}`}>
                  {label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ÁREA DE RESULTADO (SOLO LECTURA) */}
      <div className="flex-grow p-5 relative flex flex-col">
        <textarea 
          id="resultArea"
          readOnly 
          value={cleanMarkdown(markdownResult)}
          placeholder="Ingresa datos crudos a la izquierda y presiona 'Concatenar' o 'Procesar con IA' para estructurar notas. O carga un archivado desde la barra de cola lateral..."
          className="w-full flex-grow bg-transparent text-slate-300 font-mono text-xs md:text-sm outline-none resize-none scrollbar-thin whitespace-pre-wrap leading-relaxed focus:ring-0"
          style={{ fontVariantLigatures: 'none' }}
        />
      </div>

      {/* Footer Informativo del Agente */}
      <div className="bg-slate-950/80 border-t border-slate-800/80 px-5 py-3.5 flex justify-between items-center text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-indigo-500" />
          PostgreSQL + pgvector Submodule Pre-set
        </span>
        <span>Markdown Standard</span>
      </div>
    </section>
  );
}
