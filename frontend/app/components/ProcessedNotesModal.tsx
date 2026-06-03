import React, { useState } from "react";
import { Bell, ChevronDown, ChevronRight, X, FileText } from "lucide-react";

interface ProcessedNote {
  id: string;
  class_title: string;
  course_name: string;
  processed_at: string | null;
}

interface ProcessedNotesModalProps {
  isOpen: boolean;
  notes: ProcessedNote[];
  onClose: () => void;
  onSelectNote: (noteId: string) => void;
}

export function ProcessedNotesModal({ isOpen, notes, onClose, onSelectNote }: ProcessedNotesModalProps) {
  const [isListExpanded, setIsListExpanded] = useState(false);

  if (!isOpen || notes.length === 0) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-slate-900/95 border border-slate-700/60 rounded-2xl shadow-2xl shadow-indigo-950/30 animate-fade-in glassmorphism overflow-hidden">
        
        {/* Efecto decorativo superior */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500" />

        {/* Botón cerrar */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-all cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Contenido */}
        <div className="p-6 pt-8">
          {/* Icono y título */}
          <div className="flex flex-col items-center text-center mb-6">
            <div className="w-14 h-14 rounded-full bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center mb-4">
              <Bell className="w-7 h-7 text-indigo-400" />
            </div>
            <h3 className="text-lg font-bold text-slate-100 mb-1.5">
              Mientras no estabas se {notes.length === 1 ? "procesó" : "procesaron"}{" "}
              <span className="text-indigo-400">{notes.length}</span>{" "}
              {notes.length === 1 ? "nota" : "notas"}
            </h3>
            <p className="text-xs text-slate-400 max-w-xs leading-relaxed">
              El agente automático procesó tus apuntes pendientes en segundo plano.
            </p>
          </div>

          {/* Toggle list expandible */}
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl overflow-hidden mb-6">
            <button
              onClick={() => setIsListExpanded(!isListExpanded)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-slate-300 hover:text-slate-100 hover:bg-slate-800/40 transition-all cursor-pointer"
            >
              <span className="flex items-center gap-2">
                {isListExpanded ? (
                  <ChevronDown className="w-4 h-4 text-indigo-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-indigo-400" />
                )}
                Tareas analizadas
              </span>
              <span className="px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-[10px] font-bold text-indigo-400">
                {notes.length}
              </span>
            </button>

            {isListExpanded && (
              <div className="border-t border-slate-800/60 max-h-48 overflow-y-auto scrollbar-thin">
                {notes.map((note) => (
                  <button
                    key={note.id}
                    onClick={() => onSelectNote(note.id)}
                    className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-indigo-500/10 transition-all border-b border-slate-800/40 last:border-b-0 cursor-pointer group"
                  >
                    <FileText className="w-4 h-4 text-slate-500 group-hover:text-indigo-400 mt-0.5 flex-shrink-0 transition-colors" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-200 group-hover:text-indigo-300 truncate transition-colors">
                        {note.class_title}
                      </p>
                      <p className="text-[11px] text-slate-500 truncate">
                        {note.course_name}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Botón de confirmación */}
          <button
            onClick={onClose}
            className="w-full bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold py-3 px-6 rounded-xl border border-indigo-500/30 hover:border-indigo-400/50 shadow-lg shadow-indigo-950/30 transition-all active:scale-[0.98] cursor-pointer"
          >
            Entendido
          </button>
        </div>
      </div>
    </div>
  );
}
