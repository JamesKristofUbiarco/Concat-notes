import React from "react";
import { 
  History, X, Archive, Folder, Trash2, ChevronRight, ExternalLink, Plus, Layers, Edit
} from "lucide-react";
import { QueueItem, SidebarTab } from "../types";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  sidebarTab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
  pendingItems: QueueItem[];
  processedItems: QueueItem[];
  courses: string[];
  selectedQueueItemId: string | null;
  selectedCourse: string | null;
  onLoadItem: (item: QueueItem) => void;
  onLoadArchiveResult: (item: QueueItem) => void;
  onLoadCourse: (courseName: string) => void;
  onDeleteItem: (id: string, e: React.MouseEvent) => void;
  onRenameCourse: (oldName: string, newName: string) => Promise<void>;
  onNewNote: () => void;
  onOpenTemplateModal: () => void;
  onOpenReorderModal: () => void;
}

export function Sidebar({
  isOpen,
  onClose,
  sidebarTab,
  onTabChange,
  pendingItems,
  processedItems,
  courses,
  selectedQueueItemId,
  selectedCourse,
  onLoadItem,
  onLoadArchiveResult,
  onLoadCourse,
  onDeleteItem,
  onRenameCourse,
  onNewNote,
  onOpenTemplateModal,
  onOpenReorderModal,
}: SidebarProps) {
  const [editingCourse, setEditingCourse] = React.useState<string | null>(null);
  const [courseRenameValue, setCourseRenameValue] = React.useState<string>("");
  return (
    <>
      <div className={`fixed inset-y-0 left-0 w-80 bg-slate-900 border-r border-slate-800 z-40 transition-transform duration-300 transform glassmorphism shadow-2xl flex flex-col ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      }`}>
        {/* Header del Sidebar */}
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/60">
          <span className="text-sm font-extrabold text-slate-200 tracking-wider uppercase flex items-center gap-2">
            <History className="w-4 h-4 text-indigo-400" />
            Gestor de Apuntes
          </span>
          <button 
            onClick={onClose}
            className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Selector de pestañas */}
        <div className="grid grid-cols-3 border-b border-slate-800 p-2 bg-slate-950/20">
          <button 
            onClick={() => onTabChange("pending")}
            className={`py-2 px-1 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              sidebarTab === "pending" 
                ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/20" 
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Archive className="w-3 h-3" />
            Cola ({pendingItems.length})
          </button>
          <button 
            onClick={() => onTabChange("processed")}
            className={`py-2 px-1 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              sidebarTab === "processed" 
                ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/20" 
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <History className="w-3 h-3" />
            Archivados ({processedItems.length})
          </button>
          <button 
            onClick={() => onTabChange("courses")}
            className={`py-2 px-1 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              sidebarTab === "courses" 
                ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/20" 
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Folder className="w-3 h-3" />
            Cursos ({courses.length})
          </button>
        </div>

        {/* Listado del Sidebar */}
        <div className="flex-grow overflow-y-auto p-4 flex flex-col gap-3 scrollbar-thin">
          {sidebarTab === "pending" ? (
            pendingItems.length === 0 ? (
              <div className="text-center py-12 text-slate-500 flex flex-col items-center gap-3">
                <Archive className="w-10 h-10 text-slate-700 animate-bounce" />
                <p className="text-xs">No hay fichas pendientes en la cola activa.</p>
              </div>
            ) : (
              pendingItems.map((item) => (
                <div 
                  key={item.id} 
                  onClick={() => onLoadItem(item)}
                  className={`group border rounded-xl p-3.5 transition-all-custom cursor-pointer flex flex-col gap-2 relative overflow-hidden ${
                    selectedQueueItemId === item.id 
                      ? "bg-indigo-950/20 border-indigo-500/50 glow-indigo" 
                      : "bg-slate-950/40 border-slate-800 hover:border-slate-700/80"
                  }`}
                >
                  <span className="absolute top-3 right-3 w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                  <div className="pr-4">
                    <span className="text-[10px] font-semibold text-slate-500 block uppercase mb-0.5">{item.courseName}</span>
                    <h4 className="text-xs font-bold text-slate-200 line-clamp-1 group-hover:text-indigo-400 transition-colors">{item.classTitle}</h4>
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-slate-500 border-t border-slate-800/60 pt-2.5 mt-1">
                    <span>{item.createdAt.split(",")[0]}</span>
                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button 
                        type="button" 
                        title="Eliminar"
                        onClick={(e) => onDeleteItem(item.id, e)}
                        className="p-1 text-rose-400 hover:bg-rose-500/10 rounded"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                      <ChevronRight className="w-3.5 h-3.5 text-indigo-400" />
                    </div>
                  </div>
                </div>
              ))
            )
          ) : sidebarTab === "processed" ? (
            processedItems.length === 0 ? (
              <div className="text-center py-12 text-slate-500 flex flex-col items-center gap-3">
                <History className="w-10 h-10 text-slate-700" />
                <p className="text-xs">El archivo histórico está vacío.</p>
              </div>
            ) : (
              processedItems.map((item) => (
                <div 
                  key={item.id} 
                  onClick={() => onLoadArchiveResult(item)}
                  className="group bg-slate-950/40 border border-slate-800 hover:border-slate-700/80 rounded-xl p-3.5 transition-all-custom cursor-pointer flex flex-col gap-2 relative"
                >
                  <span className="absolute top-3.5 right-3.5 w-2 h-2 rounded-full bg-emerald-400" />
                  <div>
                    <span className="text-[10px] font-semibold text-slate-500 block uppercase mb-0.5">{item.courseName}</span>
                    <h4 className="text-xs font-bold text-slate-200 line-clamp-1 group-hover:text-indigo-400 transition-colors">{item.classTitle}</h4>
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-slate-500 border-t border-slate-800/60 pt-2.5 mt-1">
                    <span>Procesado</span>
                    <div className="flex items-center gap-1.5">
                      <button 
                        type="button" 
                        title="Cargar Ficha Cruda"
                        onClick={(e) => {
                          e.stopPropagation();
                          onLoadItem(item);
                        }}
                        className="p-1 text-blue-400 hover:bg-blue-500/10 rounded text-[9px] font-bold flex items-center gap-0.5"
                      >
                        <ExternalLink className="w-3 h-3" />
                        Editar
                      </button>
                      <button 
                        type="button" 
                        title="Eliminar"
                        onClick={(e) => onDeleteItem(item.id, e)}
                        className="p-1 text-rose-400 hover:bg-rose-500/10 rounded"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )
          ) : (
            courses.length === 0 ? (
              <div className="text-center py-12 text-slate-500 flex flex-col items-center gap-3">
                <Folder className="w-10 h-10 text-slate-700" />
                <p className="text-xs">No hay cursos procesados aún.</p>
              </div>
            ) : (
              courses.map((courseName, idx) => (
                <div 
                  key={`course-${idx}`} 
                  onClick={() => onLoadCourse(courseName)}
                  className={`group border rounded-xl p-3.5 transition-all-custom cursor-pointer flex flex-col gap-2 relative overflow-hidden ${
                    selectedCourse === courseName 
                      ? "bg-emerald-950/20 border-emerald-500/50 glow-emerald" 
                      : "bg-slate-950/40 border-slate-800 hover:border-slate-700/80"
                  }`}
                >
                  <span className="absolute top-3.5 right-3.5 w-2 h-2 rounded-full bg-emerald-400" />
                  <div>
                    <span className="text-[10px] font-semibold text-slate-500 block uppercase mb-0.5">MÓDULO DE CURSO MOC</span>
                    {editingCourse === courseName ? (
                      <input
                        type="text"
                        value={courseRenameValue}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => setCourseRenameValue(e.target.value)}
                        onKeyDown={async (e) => {
                          if (e.key === "Enter") {
                            e.stopPropagation();
                            if (courseRenameValue.trim() && courseRenameValue.trim() !== courseName) {
                              await onRenameCourse(courseName, courseRenameValue.trim());
                            }
                            setEditingCourse(null);
                          } else if (e.key === "Escape") {
                            e.stopPropagation();
                            setEditingCourse(null);
                          }
                        }}
                        onBlur={async () => {
                          if (courseRenameValue.trim() && courseRenameValue.trim() !== courseName) {
                            await onRenameCourse(courseName, courseRenameValue.trim());
                          }
                          setEditingCourse(null);
                        }}
                        className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                        autoFocus
                      />
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <h4 className="text-xs font-bold text-slate-200 line-clamp-1 group-hover:text-emerald-400 transition-colors">{courseName}</h4>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingCourse(courseName);
                            setCourseRenameValue(courseName);
                          }}
                          className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-all shrink-0 cursor-pointer"
                          title="Renombrar curso"
                        >
                          <Edit className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )
          )}
        </div>
        
        {/* Botones inferiores */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/40 flex flex-col gap-2">
          {sidebarTab === "courses" && selectedCourse && (
            <button 
              onClick={onOpenReorderModal}
              className="w-full py-2.5 px-4 bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-400 font-bold rounded-xl text-xs flex justify-center items-center gap-2 cursor-pointer transition-all active:scale-[0.98]"
            >
              <History className="w-4 h-4" />
              Reordenar Clases
            </button>
          )}
          <button 
            onClick={onOpenTemplateModal}
            className="w-full py-2.5 px-4 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 text-emerald-400 font-bold rounded-xl text-xs flex justify-center items-center gap-2 cursor-pointer transition-all active:scale-[0.98]"
          >
            <Layers className="w-4 h-4" />
            Nueva Ficha desde plantilla
          </button>
          <button 
            onClick={onNewNote}
            className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs flex justify-center items-center gap-2 cursor-pointer shadow-md transition-all active:scale-[0.98]"
          >
            <Plus className="w-4 h-4" />
            Nueva Ficha
          </button>
        </div>
      </div>

      {/* Backdrop */}
      {isOpen && (
        <div 
          onClick={onClose}
          className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs z-30 transition-opacity"
        />
      )}
    </>
  );
}
