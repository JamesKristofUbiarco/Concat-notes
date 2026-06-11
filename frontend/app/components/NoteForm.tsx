import React from "react";
import { 
  Zap, Layers, Trash2, Eraser, PlusCircle, Terminal, Code2,
  BookOpen, User, Folder, FileText, MessageSquareCode, Globe,
  CornerDownRight, Save, Clock
} from "lucide-react";
import { CodeSnippet, CommandSnippet } from "../schemas/noteSchema";

interface NoteFormProps {
  // Form values
  writingMode: string; setWritingMode: (v: string) => void;
  platform: string; setPlatform: (v: string) => void;
  courseName: string; setCourseName: (v: string) => void;
  teacher: string; setTeacher: (v: string) => void;
  courseModule: string; setCourseModule: (v: string) => void;
  classTitle: string; setClassTitle: (v: string) => void;
  transcription: string; setTranscription: (v: string) => void;
  classSummary: string; setClassSummary: (v: string) => void;
  myNotes: string; setMyNotes: (v: string) => void;
  classMinutes: string; setClassMinutes: (v: string) => void;
  // Snippets
  codeSnippets: CodeSnippet[];
  commandSnippets: CommandSnippet[];
  addCodeSnippet: () => void;
  removeCodeSnippet: (id: string) => void;
  updateCodeSnippet: (id: string, field: "lang" | "code", value: string) => void;
  addCommandSnippet: () => void;
  removeCommandSnippet: (id: string) => void;
  updateCommandSnippet: (id: string, field: "order" | "lang" | "cmd", value: string) => void;
  // Errors
  errors: Record<string, string>;
  setErrors: (errors: Record<string, string>) => void;
  // State indicators
  selectedQueueItemId: string | null;
  isAIProcessing: boolean;
  // Actions
  onSaveToQueue: () => void;
  onConcatenate: () => void;
  onAIProcess: () => void;
  onClearFromModule: () => void;
  onClearFromTitle: () => void;
  onClearAll: () => void;
}

export function NoteForm({
  writingMode, setWritingMode,
  platform, setPlatform,
  courseName, setCourseName,
  teacher, setTeacher,
  courseModule, setCourseModule,
  classTitle, setClassTitle,
  transcription, setTranscription,
  classSummary, setClassSummary,
  myNotes, setMyNotes,
  classMinutes, setClassMinutes,
  codeSnippets, commandSnippets,
  addCodeSnippet, removeCodeSnippet, updateCodeSnippet,
  addCommandSnippet, removeCommandSnippet, updateCommandSnippet,
  errors, setErrors,
  selectedQueueItemId, isAIProcessing,
  onSaveToQueue, onConcatenate, onAIProcess,
  onClearFromModule, onClearFromTitle, onClearAll,
}: NoteFormProps) {
  return (
    <section className="lg:col-span-7 flex flex-col gap-6 bg-slate-900/40 rounded-2xl p-5 md:p-7 border border-slate-800/80 glassmorphism shadow-2xl relative">
      
      {/* Título de la Sección */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-md font-bold text-slate-200 tracking-wide uppercase flex items-center gap-2">
            <span className="w-1.5 h-4 rounded bg-indigo-500" />
            Ficha Cruda de Entrada
          </h2>
          {selectedQueueItemId && (
            <span className="px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-[10px] font-bold text-indigo-400 animate-pulse flex items-center gap-1">
              <CornerDownRight className="w-3 h-3" />
              Editando desde la Cola
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">* Campos obligatorios</span>
      </div>

      <div className="flex flex-col gap-5">
        {/* Modo de Redacción */}
        <div>
          <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
            Modo de redacción
          </label>
          <select 
            value={writingMode} 
            onChange={(e) => setWritingMode(e.target.value)}
            className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom text-slate-300"
          >
            <option value="">Dejar vacío</option>
            <option value="Mantener el contenido palabra por palabra">Mantener el contenido palabra por palabra</option>
            <option value="Mejorar el contenido pero manteniendo la longitud">Mejorar el contenido pero manteniendo la longitud</option>
            <option value="Resumir el contenido pero manteniendo toda la información importante">Resumir el contenido pero manteniendo toda la información importante</option>
            <option value="Mantener todos los snippets de código intactos">Mantener todos los snippets de código intactos</option>
          </select>
        </div>

        {/* Grid 2 Columnas: Plataforma y Profesor */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div>
            <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5 text-blue-400" />
              Plataforma
            </label>
            <input 
              type="text" 
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              placeholder="Ej. Coursera, Udemy, Platzi..." 
              className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom text-slate-300"
            />
          </div>
          <div>
            <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-indigo-400" />
              Profesor
            </label>
            <input 
              type="text" 
              value={teacher}
              onChange={(e) => setTeacher(e.target.value)}
              placeholder="Ej. Juan Pérez..." 
              className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom text-slate-300"
            />
          </div>
        </div>

        {/* Nombre del Curso - REQUERIDO */}
        <div id="input-field-courseName">
          <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
              Nombre del curso *
            </span>
            {errors.courseName && <span className="text-[11px] font-medium text-rose-400 animate-pulse">{errors.courseName}</span>}
          </label>
          <input 
            type="text" 
            value={courseName}
            onChange={(e) => {
              setCourseName(e.target.value);
              if (errors.courseName) setErrors({ ...errors, courseName: "" });
            }}
            placeholder="Ej. Desarrollo Web Full Stack..." 
            className={`w-full bg-slate-950/70 border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 transition-all-custom text-slate-300 ${
              errors.courseName 
                ? "border-rose-500/80 focus:border-rose-500/90 focus:ring-rose-500/20 ring-1 ring-rose-500/30" 
                : "border-slate-800 focus:border-indigo-500/60 focus:ring-indigo-500/20"
            }`}
          />
        </div>

        {/* Grid 3 Columnas: Módulo, Clase y Minutos */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div>
            <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
              <Folder className="w-3.5 h-3.5 text-blue-400" />
              Módulo del curso
            </label>
            <input 
              type="text" 
              value={courseModule}
              onChange={(e) => setCourseModule(e.target.value)}
              placeholder="Ej. Módulo 3: React Avanzado..." 
              className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom text-slate-300"
            />
          </div>
          <div id="input-field-classTitle">
            <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-indigo-400" />
                Título de la clase *
              </span>
              {errors.classTitle && <span className="text-[11px] font-medium text-rose-400 animate-pulse">{errors.classTitle}</span>}
            </label>
            <input 
              type="text" 
              value={classTitle}
              onChange={(e) => {
                setClassTitle(e.target.value);
                if (errors.classTitle) setErrors({ ...errors, classTitle: "" });
              }}
              placeholder="Ej. Introducción a los Hooks..." 
              className={`w-full bg-slate-950/70 border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 transition-all-custom text-slate-300 ${
                errors.classTitle 
                  ? "border-rose-500/80 focus:border-rose-500/90 focus:ring-rose-500/20 ring-1 ring-rose-500/30" 
                  : "border-slate-800 focus:border-indigo-500/60 focus:ring-indigo-500/20"
              }`}
            />
          </div>
          <div id="input-field-classMinutes">
            <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-indigo-400" />
                Minutos de clase *
              </span>
              {errors.classMinutes && <span className="text-[11px] font-medium text-rose-400 animate-pulse">{errors.classMinutes}</span>}
            </label>
            <input 
              type="number" 
              min="1"
              value={classMinutes}
              onChange={(e) => {
                setClassMinutes(e.target.value);
                if (errors.classMinutes) setErrors({ ...errors, classMinutes: "" });
              }}
              placeholder="Ej. 45" 
              className={`w-full bg-slate-950/70 border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 transition-all-custom text-slate-300 ${
                errors.classMinutes 
                  ? "border-rose-500/80 focus:border-rose-500/90 focus:ring-rose-500/20 ring-1 ring-rose-500/30" 
                  : "border-slate-800 focus:border-indigo-500/60 focus:ring-indigo-500/20"
              }`}
            />
          </div>
        </div>

        {/* Transcripción */}
        <div>
          <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
            <MessageSquareCode className="w-3.5 h-3.5 text-emerald-400" />
            Transcripción
          </label>
          <textarea 
            rows={4} 
            value={transcription}
            onChange={(e) => setTranscription(e.target.value)}
            placeholder="Pega aquí la transcripción cruda de la clase..."
            className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom resize-y text-slate-300 text-sm font-mono scrollbar-thin"
          />
        </div>

        {/* Resumen */}
        <div>
          <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
            Resumen de la clase
          </label>
          <textarea 
            rows={3} 
            value={classSummary}
            onChange={(e) => setClassSummary(e.target.value)}
            placeholder="Escribe un breve resumen preliminar de lo expuesto en la clase..."
            className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom resize-y text-slate-300 text-sm"
          />
        </div>

        {/* Notas Propias */}
        <div>
          <label className="block text-xs md:text-sm font-semibold mb-2 text-slate-300 flex items-center gap-1.5">
            Notas propias
          </label>
          <textarea 
            rows={4} 
            value={myNotes}
            onChange={(e) => setMyNotes(e.target.value)}
            placeholder="Añade observaciones, comentarios breves, código rápido o puntos clave..."
            className="w-full bg-slate-950/70 border border-slate-800 focus:border-indigo-500/60 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all-custom resize-y text-slate-300 text-sm"
          />
        </div>

        {/* SNIPPETS DE CÓDIGO */}
        <div className="border-t border-slate-800/80 pt-6">
          <div className="flex justify-between items-center mb-4">
            <label className="block text-xs md:text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Code2 className="w-4 h-4 text-sky-400" />
              Snippets de código
            </label>
            <button type="button" onClick={addCodeSnippet} className="text-xs flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 hover:scale-[1.02] font-semibold transition-all">
              <PlusCircle className="w-4 h-4" />
              Añadir otro snippet
            </button>
          </div>
          <div className="flex flex-col gap-4">
            {codeSnippets.map((snippet) => (
              <div key={snippet.id} className="group relative bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 transition-all-custom hover:border-slate-700/60 focus-within:border-indigo-500/40">
                <div className="flex justify-between items-center mb-3">
                  <input 
                    type="text" placeholder="Lenguaje (ej. js, typescript, sql)..." 
                    value={snippet.lang} onChange={(e) => updateCodeSnippet(snippet.id, "lang", e.target.value)}
                    className="w-full md:w-1/3 bg-slate-900 border border-slate-800 rounded-lg text-xs px-3 py-2 text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-all-custom"
                  />
                  {codeSnippets.length > 1 && (
                    <button type="button" title="Eliminar snippet" onClick={() => removeCodeSnippet(snippet.id)} className="p-1.5 text-rose-400/70 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all animate-fade-in">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <textarea 
                  rows={4} placeholder="Pega tu fragmento de código estructurado aquí..."
                  value={snippet.code} onChange={(e) => updateCodeSnippet(snippet.id, "code", e.target.value)}
                  className="w-full bg-slate-950 text-emerald-400 font-mono text-xs md:text-sm border border-slate-900 focus:border-indigo-500/30 rounded-lg px-4 py-3 focus:outline-none focus:ring-1 focus:ring-indigo-500/10 resize-y"
                />
              </div>
            ))}
          </div>
        </div>

        {/* SNIPPETS DE COMANDOS */}
        <div className="border-t border-slate-800/80 pt-6">
          <div className="flex justify-between items-center mb-4">
            <label className="block text-xs md:text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Terminal className="w-4 h-4 text-amber-400" />
              Snippets de comandos
            </label>
            <button type="button" onClick={addCommandSnippet} className="text-xs flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 hover:scale-[1.02] font-semibold transition-all">
              <PlusCircle className="w-4 h-4" />
              Añadir otro comando
            </button>
          </div>
          <div className="flex flex-col gap-4">
            {commandSnippets.map((snippet) => (
              <div key={snippet.id} className="group relative bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 transition-all-custom hover:border-slate-700/60 focus-within:border-indigo-500/40">
                <div className="flex justify-between items-start md:items-center gap-3 mb-3">
                  <div className="flex flex-col md:flex-row gap-3 w-full md:w-3/4">
                    <input type="text" placeholder="Orden (ej. Paso 1)" value={snippet.order} onChange={(e) => updateCommandSnippet(snippet.id, "order", e.target.value)} className="w-full md:w-1/2 bg-slate-900 border border-slate-800 rounded-lg text-xs px-3 py-2 text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-all-custom" />
                    <input type="text" placeholder="Lenguaje (ej. bash)" value={snippet.lang} onChange={(e) => updateCommandSnippet(snippet.id, "lang", e.target.value)} className="w-full md:w-1/2 bg-slate-900 border border-slate-800 rounded-lg text-xs px-3 py-2 text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-all-custom" />
                  </div>
                  {commandSnippets.length > 1 && (
                    <button type="button" title="Eliminar comando" onClick={() => removeCommandSnippet(snippet.id)} className="p-1.5 text-rose-400/70 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all animate-fade-in">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <textarea 
                  rows={2} placeholder="Pega tu comando ejecutable de terminal..."
                  value={snippet.cmd} onChange={(e) => updateCommandSnippet(snippet.id, "cmd", e.target.value)}
                  className="w-full bg-slate-950 text-amber-400 font-mono text-xs md:text-sm border border-slate-900 focus:border-indigo-500/30 rounded-lg px-4 py-3 focus:outline-none focus:ring-1 focus:ring-indigo-500/10 resize-y"
                />
              </div>
            ))}
          </div>
        </div>

        {/* BOTONES DE LIMPIEZA */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 border-t border-slate-800/80 pt-6">
          <button type="button" onClick={onClearFromModule} className="w-full text-xs font-semibold py-3 px-3.5 bg-slate-900 border border-slate-800 hover:border-slate-700/60 hover:bg-slate-850 hover:text-slate-200 text-slate-400 rounded-xl transition-all-custom flex justify-center items-center gap-2 group cursor-pointer">
            <Eraser className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
            Desde módulo
          </button>
          <button type="button" onClick={onClearFromTitle} className="w-full text-xs font-semibold py-3 px-3.5 bg-slate-900 border border-slate-800 hover:border-slate-700/60 hover:bg-slate-850 hover:text-slate-200 text-slate-400 rounded-xl transition-all-custom flex justify-center items-center gap-2 group text-center leading-tight cursor-pointer">
            <Eraser className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
            Desde Título clase
          </button>
          <button type="button" onClick={onClearAll} className="w-full text-xs font-semibold py-3 px-3.5 bg-rose-950/20 border border-rose-900/30 hover:border-rose-500/40 hover:bg-rose-950/40 text-rose-400 rounded-xl transition-all-custom flex justify-center items-center gap-2 cursor-pointer">
            <Trash2 className="w-4 h-4" />
            Borrar todo
          </button>
        </div>

        {/* BOTONES DE GUARDADO Y CONCATENACIÓN */}
        <div className="flex flex-col sm:flex-row gap-4 mt-2">
          <button type="button" id="saveQueueBtn" onClick={onSaveToQueue} className="flex-1 bg-gradient-to-r from-indigo-700 to-indigo-850 hover:from-indigo-650 hover:to-indigo-800 text-slate-100 font-bold py-3.5 px-6 rounded-xl border border-indigo-500/35 hover:border-indigo-400/50 shadow-lg shadow-indigo-950/25 transition-all-custom flex justify-center items-center gap-2 active:scale-[0.98] cursor-pointer">
            <Save className="w-5 h-5 text-indigo-300" />
            {selectedQueueItemId ? "Actualizar en Cola" : "Guardar en Cola"}
          </button>
          <button type="button" onClick={onConcatenate} className="flex-1 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-bold py-3.5 px-6 rounded-xl shadow-lg shadow-blue-500/10 hover:shadow-blue-500/20 transition-all-custom flex justify-center items-center gap-2 active:scale-[0.98] cursor-pointer">
            <Layers className="w-5 h-5" />
            Concatenar Markdown
          </button>
          <button type="button" onClick={onAIProcess} disabled={isAIProcessing} className="flex-1 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-white font-bold py-3.5 px-6 rounded-xl shadow-lg shadow-violet-500/10 hover:shadow-violet-500/20 transition-all-custom flex justify-center items-center gap-2 active:scale-[0.98] cursor-pointer disabled:opacity-50 disabled:pointer-events-none group relative overflow-hidden">
            <Zap className="w-5 h-5 text-violet-200 group-hover:scale-110 transition-transform" />
            Procesar Ahora
          </button>
        </div>
      </div>
    </section>
  );
}
