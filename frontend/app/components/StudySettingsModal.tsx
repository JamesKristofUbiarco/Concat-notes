import React, { useState, useEffect, useRef } from "react";
import { Target, X, RefreshCw, AlertTriangle, CheckCircle2, Brain, Download, Upload } from "lucide-react";

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

interface ModelOption {
  id: string;
  name: string;
  provider: string;
}

interface AvailableModelsMap {
  synthesis: ModelOption[];
  query_expansion: ModelOption[];
  image_analysis: ModelOption[];
}

interface StudySettingsModalProps {
  isOpen: boolean;
  currentGoal: number;
  courses: string[];
  processedNotes: ProcessedNoteItem[];
  onSave: (minutes: number) => Promise<void>;
  onReprocess: (payload: { target: string; course_name?: string; note_id?: string }) => Promise<{ status: string; message: string; reprocessed: number; errors: number }>;
  onClose: () => void;
  downloadBackup: () => Promise<boolean>;
  uploadRestore: (file: File) => Promise<any>;
}

export function StudySettingsModal({
  isOpen,
  currentGoal,
  courses,
  processedNotes,
  onSave,
  onReprocess,
  onClose,
  downloadBackup,
  uploadRestore
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

  // AI Models Config State
  const [activeSynthesis, setActiveSynthesis] = useState<string>("");
  const [activeQueryExpansion, setActiveQueryExpansion] = useState<string>("");
  const [activeImageAnalysis, setActiveImageAnalysis] = useState<string>("");
  const [availableModels, setAvailableModels] = useState<AvailableModelsMap | null>(null);
  const [modelsLoading, setModelsLoading] = useState<boolean>(false);
  const [modelsError, setModelsError] = useState<string>("");

  // Backup & Restore State
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [backupLoading, setBackupLoading] = useState<boolean>(false);
  const [restoreLoading, setRestoreLoading] = useState<boolean>(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreSuccess, setRestoreSuccess] = useState<string | null>(null);
  const [showConfirmRestore, setShowConfirmRestore] = useState<boolean>(false);
  const [confirmText, setConfirmText] = useState<string>("");
  const [restoreFile, setRestoreFile] = useState<File | null>(null);

  const handleDownloadBackup = async () => {
    setBackupLoading(true);
    setRestoreError(null);
    setRestoreSuccess(null);
    try {
      const success = await downloadBackup();
      if (success) {
        setRestoreSuccess("Respaldo completo descargado exitosamente.");
      } else {
        setRestoreError("Error al generar o descargar el respaldo.");
      }
    } catch (err: any) {
      setRestoreError(err.message || "Error al descargar el respaldo.");
    } finally {
      setBackupLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setRestoreFile(file);
    setShowConfirmRestore(true);
    setConfirmText("");
    setRestoreError(null);
    setRestoreSuccess(null);
  };

  const cancelRestore = () => {
    setShowConfirmRestore(false);
    setRestoreFile(null);
    setConfirmText("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const confirmAndRestore = async () => {
    if (!restoreFile || confirmText !== "RESTAURAR") return;
    
    setRestoreLoading(true);
    setRestoreError(null);
    setRestoreSuccess(null);
    
    try {
      const res = await uploadRestore(restoreFile);
      setRestoreSuccess(`Restauración exitosa. Se restauraron ${res.images_restored} imágenes.`);
      setShowConfirmRestore(false);
      setRestoreFile(null);
      setConfirmText("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      
      // Esperar un momento para que el usuario pueda ver el mensaje y recargar la página
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (err: any) {
      setRestoreError(err.message || "Ocurrió un error al restaurar la base de datos.");
    } finally {
      setRestoreLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setGoal(currentGoal.toString());
      setError("");
      setReprocessTarget("all_dummies");
      setSelectedCourse("");
      setSelectedModule("");
      setSelectedNoteId("");
      setReprocessResult(null);
      setModelsError("");
      setRestoreError(null);
      setRestoreSuccess(null);
      setShowConfirmRestore(false);
      setConfirmText("");
      setRestoreFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      
      // Cargar configuraciones de modelos de IA
      const fetchModels = async () => {
        setModelsLoading(true);
        try {
          const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
          const res = await fetch(`${API_BASE}/api/settings/models`);
          if (res.ok) {
            const data = await res.json();
            setActiveSynthesis(data.synthesis);
            setActiveQueryExpansion(data.query_expansion);
            setActiveImageAnalysis(data.image_analysis);
            setAvailableModels(data.available);
          } else {
            setModelsError("No se pudieron cargar las opciones de modelos.");
          }
        } catch (err) {
          setModelsError("Error de conexión al cargar modelos.");
        } finally {
          setModelsLoading(false);
        }
      };
      fetchModels();
    }
  }, [isOpen, currentGoal]);

  const handleModelChange = async (role: string, modelId: string) => {
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API_BASE}/api/settings/models`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, model_id: modelId })
      });
      if (res.ok) {
        const data = await res.json();
        setActiveSynthesis(data.synthesis);
        setActiveQueryExpansion(data.query_expansion);
        setActiveImageAnalysis(data.image_analysis);
      } else {
        setModelsError("Error al guardar la selección de modelo.");
      }
    } catch (err) {
      setModelsError("Error de red al actualizar modelo.");
    }
  };

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

        {/* SECTION 1.5: IA MODELS */}
        <div className="pt-2 border-b border-slate-800/60 pb-5 mb-6">
          <h3 className="text-md font-bold text-slate-200 mb-4 flex items-center gap-2">
            <Brain className="w-5 h-5 text-indigo-400" />
            Modelos de IA (OpenRouter / Gemini)
          </h3>
          
          <p className="text-slate-400 mb-4 text-xs md:text-sm leading-relaxed">
            Elige los proveedores y modelos de inteligencia artificial para cada tarea del sistema.
          </p>

          {modelsLoading ? (
            <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
              <RefreshCw className="w-3 h-3 animate-spin" />
              Cargando modelos...
            </div>
          ) : modelsError ? (
            <p className="text-rose-500 text-xs py-2">{modelsError}</p>
          ) : availableModels && (
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Síntesis (Nota principal)
                </label>
                <select
                  value={activeSynthesis}
                  onChange={(e) => handleModelChange("synthesis", e.target.value)}
                  className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all cursor-pointer"
                >
                  {availableModels.synthesis.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.provider})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Búsqueda (Query Expansion RAG)
                </label>
                <select
                  value={activeQueryExpansion}
                  onChange={(e) => handleModelChange("query_expansion", e.target.value)}
                  className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all cursor-pointer"
                >
                  {availableModels.query_expansion.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.provider})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Visión (Análisis de Imágenes)
                </label>
                <select
                  value={activeImageAnalysis}
                  onChange={(e) => handleModelChange("image_analysis", e.target.value)}
                  className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all cursor-pointer"
                >
                  {availableModels.image_analysis.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.provider})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

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

        {/* SECTION 3: BACKUP & RESTORE */}
        <div className="pt-6 border-t border-slate-800/60 mt-6 pb-2">
          <h3 className="text-md font-bold text-slate-200 mb-4 flex items-center gap-2">
            <Download className="w-5 h-5 text-indigo-400" />
            Respaldo y Restauración de Datos
          </h3>
          <p className="text-slate-400 text-xs md:text-sm leading-relaxed mb-4">
            Descarga un respaldo completo (base de datos con embeddings pgvector e imágenes físicas de RustFS) o restaura el sistema desde un archivo previamente generado.
          </p>

          <div className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleDownloadBackup}
                disabled={backupLoading || restoreLoading}
                className="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed border border-slate-800 hover:border-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2"
              >
                {backupLoading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                    Generando respaldo...
                  </>
                ) : (
                  <>
                    <Download className="w-3.5 h-3.5 text-indigo-400" />
                    Descargar Respaldo Completo
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={backupLoading || restoreLoading}
                className="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed border border-slate-800 hover:border-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2"
              >
                <Upload className="w-3.5 h-3.5 text-indigo-400" />
                Restaurar desde Archivo
              </button>
              
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                accept=".zip"
                className="hidden"
              />
            </div>

            {/* Error or Success Alert */}
            {(restoreError || restoreSuccess) && (
              <div className={`p-3 rounded-xl border text-xs flex items-start gap-2 ${
                restoreSuccess 
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" 
                  : "bg-rose-500/10 border-rose-500/30 text-rose-400"
              }`}>
                {restoreSuccess ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                )}
                <span>{restoreSuccess || restoreError}</span>
              </div>
            )}

            {/* Inline Confirmation Card */}
            {showConfirmRestore && restoreFile && (
              <div className="p-4 rounded-xl border border-rose-500/30 bg-rose-500/5 space-y-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="text-xs font-bold text-rose-400">¿Estás seguro de restaurar?</h4>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Se eliminarán y reemplazarán todas las notas, embeddings e imágenes actuales con el contenido de <strong>{restoreFile.name}</strong>. Esta acción es irreversible.
                    </p>
                  </div>
                </div>

                <div>
                  <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                    Escribe <span className="text-rose-400 select-all font-mono font-bold">RESTAURAR</span> para confirmar:
                  </label>
                  <input
                    type="text"
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    placeholder="RESTAURAR"
                    className="w-full bg-slate-950/80 border border-slate-800 focus:border-rose-500 rounded-xl px-4 py-2 text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-rose-500 transition-all font-mono"
                  />
                </div>

                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={cancelRestore}
                    disabled={restoreLoading}
                    className="px-3 py-1.5 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-400 rounded-lg text-xs font-semibold transition-all cursor-pointer"
                  >
                    Cancelar
                  </button>
                  <button
                    type="button"
                    onClick={confirmAndRestore}
                    disabled={confirmText !== "RESTAURAR" || restoreLoading}
                    className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed text-white rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5"
                  >
                    {restoreLoading ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Restaurando...
                      </>
                    ) : (
                      "Confirmar Restauración"
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
