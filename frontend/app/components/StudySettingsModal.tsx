import React, { useState, useEffect } from "react";
import { Target, X, RefreshCw, AlertTriangle, CheckCircle2 } from "lucide-react";

interface CodeSnippetBase {
  id?: string;
  lang: string;
  code: string;
}

interface CommandSnippetBase {
  id?: string;
  order: string;
  lang: string;
  cmd: string;
}

interface ProcessedNoteItem {
  id: string;
  writingMode: string;
  platform: string;
  courseName: string;
  teacher: string;
  courseModule: string;
  classTitle: string;
  transcription: string;
  classSummary: string;
  myNotes: string;
  classMinutes: number;
  codeSnippets: CodeSnippetBase[];
  commandSnippets: CommandSnippetBase[];
  status: string;
  createdAt: string;
  orderIndex: number;
  structuredMarkdown?: string;
}

interface StudySettingsModalProps {
  isOpen: boolean;
  currentGoal: number;
  courses: string[];
  processedNotes: ProcessedNoteItem[];
  onSave: (minutes: number) => Promise<void>;
  onReprocess: (payload: { target: string; course_name?: string; note_id?: string }) => Promise<{ status: string; message: string; reprocessed: number; errors: number }>;
  onClose: () => void;
}

export function StudySettingsModal({
  isOpen,
  currentGoal,
  courses,
  processedNotes,
  onSave,
  onReprocess,
  onClose
}: StudySettingsModalProps) {
  const [goal, setGoal] = useState<string>("");
  const [error, setError] = useState<string>("");

  // Reprocess Embeddings State
  const [reprocessTarget, setReprocessTarget] = useState<string>("all_dummies");
  const [selectedCourse, setSelectedCourse] = useState<string>("");
  const [selectedModule, setSelectedModule] = useState<string>("");
  const [selectedNoteId, setSelectedNoteId] = useState<string>("");
  
  const [reprocessLoading, setReprocessLoading] = useState<boolean>(false);
  const [reprocessResult, setReprocessResult] = useState<{ success: boolean; message: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      setGoal(currentGoal.toString());
      setError("");
      setReprocessTarget("all_dummies");
      setSelectedCourse("");
      setSelectedModule("");
      setSelectedNoteId("");
      setReprocessResult(null);
    }
  }, [isOpen, currentGoal]);

  useEffect(() => {
    setSelectedCourse("");
    setSelectedModule("");
    setSelectedNoteId("");
    setReprocessResult(null);
  }, [reprocessTarget]);

  useEffect(() => {
    setSelectedModule("");
    setSelectedNoteId("");
  }, [selectedCourse]);

  useEffect(() => {
    setSelectedNoteId("");
  }, [selectedModule]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const minutes = parseInt(goal, 10);
    if (isNaN(minutes) || minutes < 1) {
      setError("La meta diaria debe ser de al menos 1 minuto.");
      return;
    }
    setError("");
    await onSave(minutes);
    onClose();
  };

  const handleReprocessSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setReprocessLoading(true);
    setReprocessResult(null);
    try {
      const payload: { target: string; course_name?: string; note_id?: string } = {
        target: reprocessTarget
      };
      if (reprocessTarget === "course") {
        if (!selectedCourse) {
          throw new Error("Debe seleccionar un curso.");
        }
        payload.course_name = selectedCourse;
      } else if (reprocessTarget === "individual") {
        if (!selectedNoteId) {
          throw new Error("Debe seleccionar una nota.");
        }
        payload.note_id = selectedNoteId;
      }
      
      const result = await onReprocess(payload);
      setReprocessResult({
        success: result.errors === 0,
        message: result.message
      });
    } catch (err: any) {
      setReprocessResult({
        success: false,
        message: err.message || "Error al reprocesar embeddings."
      });
    } finally {
      setReprocessLoading(false);
    }
  };

  // Computaciones reactivas para selectores
  const courseNotes = processedNotes.filter(n => n.courseName === selectedCourse);
  const modules = Array.from(new Set(courseNotes.map(n => n.courseModule || "Sin Módulo")));
  const moduleNotes = courseNotes.filter(n => (n.courseModule || "Sin Módulo") === selectedModule);

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 max-w-md w-full transition-transform transform scale-100 glow-indigo relative max-h-[90vh] overflow-y-auto scrollbar-thin">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-500 hover:text-slate-300 p-1 hover:bg-slate-800 rounded-lg transition-all"
        >
          <X className="w-4 h-4" />
        </button>

        {/* SECTION 1: STUDY GOAL */}
        <h3 className="text-md font-bold text-slate-200 mb-4 flex items-center gap-2">
          <Target className="w-5 h-5 text-indigo-400" />
          Meta de Estudio
        </h3>

        <form onSubmit={handleSubmit} className="mb-6">
          <p className="text-slate-400 mb-4 text-xs md:text-sm leading-relaxed">
            Define tu meta de estudio diaria en minutos. Los días que completes esta meta quedarán marcados como victorias en tu calendario.
          </p>

          <div className="mb-4">
            <label htmlFor="dailyGoalInput" className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Minutos diarios
            </label>
            <input
              id="dailyGoalInput"
              type="number"
              min="1"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2.5 text-slate-200 text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all placeholder:text-slate-700"
              placeholder="Ej. 60"
              required
            />
            {error && (
              <p className="text-rose-500 text-xs mt-2 font-medium">{error}</p>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-2 border-b border-slate-800/60 pb-5">
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer"
            >
              Guardar Meta
            </button>
          </div>
        </form>

        {/* SECTION 2: REPROCESS EMBEDDINGS */}
        <div className="pt-2">
          <h3 className="text-md font-bold text-slate-200 mb-4 flex items-center gap-2">
            <RefreshCw className="w-5 h-5 text-indigo-400" />
            Regenerar Embeddings (VoyageAI)
          </h3>

          <form onSubmit={handleReprocessSubmit} className="space-y-4">
            <p className="text-slate-400 text-xs md:text-sm leading-relaxed mb-2">
              Si tuviste problemas de billing con la API de Voyage, puedes regenerar los embeddings de tus apuntes procesados que quedaron guardados como "dummy".
            </p>

            <div>
              <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                Selección de alcance
              </label>
              <select
                value={reprocessTarget}
                onChange={(e) => setReprocessTarget(e.target.value)}
                className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
              >
                <option value="all_dummies">Todas las notas que no se generaron bien</option>
                <option value="course">Todas las notas de un solo curso</option>
                <option value="individual">Una sola nota individual</option>
              </select>
            </div>

            {/* Selector de curso */}
            {(reprocessTarget === "course" || reprocessTarget === "individual") && (
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Seleccionar Curso
                </label>
                <select
                  value={selectedCourse}
                  onChange={(e) => setSelectedCourse(e.target.value)}
                  required
                  className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
                >
                  <option value="">-- Seleccionar Curso --</option>
                  {courses.map((course) => (
                    <option key={course} value={course}>
                      {course}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Selector de Módulo */}
            {reprocessTarget === "individual" && selectedCourse && (
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Seleccionar Módulo
                </label>
                <select
                  value={selectedModule}
                  onChange={(e) => setSelectedModule(e.target.value)}
                  required
                  className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
                >
                  <option value="">-- Seleccionar Módulo --</option>
                  {modules.map((mod) => (
                    <option key={mod} value={mod}>
                      {mod}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Selector de Nota */}
            {reprocessTarget === "individual" && selectedCourse && selectedModule && (
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Seleccionar Nota
                </label>
                <select
                  value={selectedNoteId}
                  onChange={(e) => setSelectedNoteId(e.target.value)}
                  required
                  className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
                >
                  <option value="">-- Seleccionar Nota --</option>
                  {moduleNotes.map((note) => (
                    <option key={note.id} value={note.id}>
                      {note.classTitle}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Resultados / Errores */}
            {reprocessResult && (
              <div className={`p-3 rounded-xl border text-xs flex items-start gap-2 ${
                reprocessResult.success 
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" 
                  : "bg-rose-500/10 border-rose-500/30 text-rose-400"
              }`}>
                {reprocessResult.success ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                )}
                <span>{reprocessResult.message}</span>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:bg-slate-900 hover:text-slate-200 text-slate-400 rounded-lg text-xs font-semibold transition-all cursor-pointer"
              >
                Cerrar
              </button>
              <button
                type="submit"
                disabled={reprocessLoading || (reprocessTarget === "course" && !selectedCourse) || (reprocessTarget === "individual" && !selectedNoteId)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed text-white rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5"
              >
                {reprocessLoading ? (
                  <>
                    <RefreshCw className="w-3 h-3 animate-spin" />
                    Procesando...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-3 h-3" />
                    Regenerar
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
