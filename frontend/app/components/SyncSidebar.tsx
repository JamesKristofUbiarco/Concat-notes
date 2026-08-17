"use client";

import React from "react";
import { Folder, FolderPlus, HardDrive, ShieldAlert, X } from "lucide-react";

export type SyncFilter = "all" | "active" | "conflicts";

interface DirectoryItem { name: string; path: string }

interface SyncSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  filter: SyncFilter;
  onFilterChange: (value: SyncFilter) => void;
  destination: string;
  mounted: boolean;
  writable: boolean;
  directories: DirectoryItem[];
  currentDirectory: string;
  onBrowse: (path: string) => void;
  onChoose: (path: string) => void;
  onCreateDirectory: (name: string) => Promise<void>;
}

export function SyncSidebar(props: SyncSidebarProps) {
  const [newDirectory, setNewDirectory] = React.useState("");
  const filters: Array<{ value: SyncFilter; label: string }> = [
    { value: "all", label: "Todos" },
    { value: "active", label: "Activos" },
    { value: "conflicts", label: "Conflictos" },
  ];
  const parent = props.currentDirectory.split("/").slice(0, -1).join("/");

  return (
    <>
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-80 flex-col border-r border-slate-800 bg-slate-900 shadow-2xl transition-transform duration-300 ${props.isOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/60 p-4">
          <span className="flex items-center gap-2 text-sm font-extrabold uppercase tracking-wider text-slate-200">
            <HardDrive className="h-4 w-4 text-cyan-400" /> Herramientas de sincronización
          </span>
          <button onClick={props.onClose} className="rounded-lg border border-slate-800 p-1.5 text-slate-400 hover:text-white" aria-label="Cerrar panel">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-1 border-b border-slate-800 p-2">
          {filters.map((item) => (
            <button key={item.value} onClick={() => props.onFilterChange(item.value)} className={`rounded-lg px-2 py-2 text-xs font-bold ${props.filter === item.value ? "border border-cyan-500/30 bg-cyan-500/15 text-cyan-300" : "text-slate-400 hover:bg-slate-800"}`}>
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          <section className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-200">Carpeta montada</span>
              <span className={`h-2.5 w-2.5 rounded-full ${props.mounted && props.writable ? "bg-emerald-400" : "bg-rose-400"}`} />
            </div>
            <p className="text-[11px] leading-relaxed text-slate-500">
              {props.mounted && props.writable ? "Disponible y escribible." : "No disponible. Revisa NOTES_SYNC_PATH y reinicia Docker."}
            </p>
            <p className="mt-2 break-all rounded bg-slate-900 px-2 py-1.5 font-mono text-[10px] text-cyan-300">{props.destination}</p>
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wide text-slate-400">Elegir subcarpeta</h3>
              <button onClick={() => props.onChoose(props.currentDirectory || ".")} className="text-[10px] font-bold text-cyan-400 hover:text-cyan-200">Usar ésta</button>
            </div>
            <div className="mb-2 flex items-center gap-2 text-[10px] text-slate-500">
              <Folder className="h-3.5 w-3.5" /> {props.currentDirectory || "Raíz montada"}
            </div>
            {props.currentDirectory && (
              <button onClick={() => props.onBrowse(parent)} className="mb-1 w-full rounded-lg px-2 py-2 text-left text-xs text-slate-400 hover:bg-slate-800">↰ Carpeta anterior</button>
            )}
            <div className="space-y-1">
              {props.directories.map((directory) => (
                <button key={directory.path} onClick={() => props.onBrowse(directory.path)} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs text-slate-300 hover:bg-slate-800">
                  <Folder className="h-3.5 w-3.5 text-cyan-500" /> {directory.name}
                </button>
              ))}
            </div>
          </section>

          <form className="flex gap-2" onSubmit={async (event) => { event.preventDefault(); if (!newDirectory.trim()) return; await props.onCreateDirectory(newDirectory.trim()); setNewDirectory(""); }}>
            <input value={newDirectory} onChange={(event) => setNewDirectory(event.target.value)} placeholder="Nueva carpeta" className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs outline-none focus:border-cyan-500" />
            <button className="rounded-lg bg-cyan-600 p-2 text-white hover:bg-cyan-500" aria-label="Crear carpeta"><FolderPlus className="h-4 w-4" /></button>
          </form>

          <div className="flex gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-[11px] leading-relaxed text-amber-200/70">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" /> Las rutas quedan confinadas al montaje configurado y no siguen enlaces simbólicos.
          </div>
        </div>
      </aside>
      {props.isOpen && <button onClick={props.onClose} className="fixed inset-0 z-30 bg-black/50" aria-label="Cerrar panel lateral" />}
    </>
  );
}
