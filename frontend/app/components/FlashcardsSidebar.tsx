"use client";

import { BookOpen, ChevronRight, Layers3, X } from "lucide-react";

interface ClassNode { class_title: string; count: number }
interface ModuleNode { module_name: string; count: number; classes: ClassNode[] }
interface CourseNode { course_name: string; count: number; modules: ModuleNode[] }

interface Props {
  isOpen: boolean;
  onClose: () => void;
  tree: CourseNode[];
  course: string;
  module: string;
  classTitle: string;
  onSelect: (course: string, module: string, classTitle: string) => void;
}

export function FlashcardsSidebar({ isOpen, onClose, tree, course, module, classTitle, onSelect }: Props) {
  return (
    <>
      {isOpen && <button aria-label="Cerrar filtros" onClick={onClose} className="fixed inset-0 z-[55] bg-black/60 backdrop-blur-sm" />}
      <aside className={`fixed inset-y-0 left-0 z-[60] flex w-[min(90vw,360px)] flex-col border-r border-slate-800 bg-slate-950 shadow-2xl transition-transform duration-300 ${isOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <header className="flex items-center justify-between border-b border-slate-800 p-5">
          <div className="flex items-center gap-3"><Layers3 className="h-5 w-5 text-violet-400" /><div><h2 className="font-bold">Biblioteca</h2><p className="text-xs text-slate-500">Cursos y módulos indexados</p></div></div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white"><X className="h-5 w-5" /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-3">
          <button onClick={() => { onSelect("", "", ""); onClose(); }} className={`mb-2 flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm ${!course ? "bg-violet-500/15 text-violet-200" : "text-slate-300 hover:bg-slate-900"}`}><span className="flex items-center gap-2"><BookOpen className="h-4 w-4" />Todas las tarjetas</span><span className="text-xs text-slate-500">{tree.reduce((sum, item) => sum + item.count, 0)}</span></button>
          {tree.map((item) => (
            <div key={item.course_name} className="mb-2 rounded-xl border border-slate-800/70 bg-slate-900/40 p-2">
              <button onClick={() => { onSelect(item.course_name, "", ""); onClose(); }} className={`flex w-full items-start justify-between gap-2 rounded-lg px-2 py-2 text-left text-xs font-bold ${course === item.course_name && !module ? "text-violet-300" : "text-slate-300"}`}><span>{item.course_name}</span><span className="shrink-0 text-slate-600">{item.count}</span></button>
              <div className="mt-1 space-y-1 border-l border-slate-700 pl-2">
                {item.modules.map((child) => <div key={child.module_name}><button onClick={() => { onSelect(item.course_name, child.module_name, ""); onClose(); }} className={`flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left text-[11px] ${course === item.course_name && module === child.module_name && !classTitle ? "bg-violet-500/15 text-violet-200" : "text-slate-500 hover:bg-slate-800 hover:text-slate-300"}`}><span className="flex min-w-0 items-center gap-1"><ChevronRight className="h-3 w-3 shrink-0" /><span className="truncate">{child.module_name}</span></span><span>{child.count}</span></button><div className="ml-4 border-l border-slate-800 pl-2">{child.classes.map((classNode) => <button key={classNode.class_title} onClick={() => { onSelect(item.course_name, child.module_name, classNode.class_title); onClose(); }} className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-[10px] ${classTitle === classNode.class_title ? "text-violet-300" : "text-slate-600 hover:text-slate-300"}`}><span className="truncate">{classNode.class_title}</span><span>{classNode.count}</span></button>)}</div></div>)}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
