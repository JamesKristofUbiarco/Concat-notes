import React from "react";
import { Layers } from "lucide-react";

interface TemplateModalProps {
  isOpen: boolean;
  courses: string[];
  modules: string[];
  selectedCourse: string;
  selectedModule: string;
  onCourseChange: (course: string) => void;
  onModuleChange: (module: string) => void;
  onCreate: () => void;
  onClose: () => void;
}

export function TemplateModal({
  isOpen,
  courses,
  modules,
  selectedCourse,
  selectedModule,
  onCourseChange,
  onModuleChange,
  onCreate,
  onClose,
}: TemplateModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 max-w-sm w-full transition-transform transform scale-100 glow-emerald">
        <h3 className="text-md font-bold text-slate-200 mb-3.5 flex items-center gap-2">
          <Layers className="w-5 h-5 text-emerald-500" />
          Crear desde Plantilla
        </h3>
        
        <p className="text-slate-400 mb-4 text-xs md:text-sm leading-relaxed">
          Selecciona el curso base. Se conservarán los metadatos generales (curso, plataforma, profesor, etc.) pero se limpiarán los detalles de la clase y se creará una ficha completamente nueva.
        </p>

        <div className="mb-4">
          <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Curso Base</label>
          <select 
            value={selectedCourse}
            onChange={(e) => onCourseChange(e.target.value)}
            className="w-full bg-slate-950/50 border border-slate-700/50 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 outline-none transition-all"
          >
            <option value="">Selecciona un curso...</option>
            {courses.map((course, idx) => (
              <option key={idx} value={course}>{course}</option>
            ))}
          </select>
        </div>

        {selectedCourse && modules.length > 0 && (
          <div className="mb-6 animate-fade-in">
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Módulo (Opcional)</label>
            <select 
              value={selectedModule}
              onChange={(e) => onModuleChange(e.target.value)}
              className="w-full bg-slate-950/50 border border-slate-700/50 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 outline-none transition-all"
            >
              <option value="">Heredar módulo base...</option>
              {modules.map((mod, idx) => (
                <option key={idx} value={mod}>{mod}</option>
              ))}
            </select>
          </div>
        )}
        
        <div className="flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 bg-slate-950 border border-slate-800 hover:bg-slate-900 hover:text-slate-200 text-slate-400 rounded-lg text-xs font-semibold transition-all cursor-pointer"
          >
            Cancelar
          </button>
          <button 
            onClick={onCreate}
            disabled={!selectedCourse}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${!selectedCourse ? "bg-emerald-900/50 text-emerald-700 cursor-not-allowed" : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20"}`}
          >
            Crear nueva ficha
          </button>
        </div>
      </div>
    </div>
  );
}
