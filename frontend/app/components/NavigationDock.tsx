"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FilePenLine, FolderSync, Layers3 } from "lucide-react";

const modules = [
  { href: "/notes", label: "Notas", icon: FilePenLine },
  { href: "/flashcards", label: "Flashcards", icon: Layers3 },
  { href: "/sync", label: "Sincronización", icon: FolderSync },
];

export function NavigationDock() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Secciones principales"
      className="fixed z-50 bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-2xl border border-slate-700/80 bg-slate-900/90 p-1.5 shadow-2xl shadow-black/40 backdrop-blur-xl"
    >
      {modules.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`min-w-24 rounded-xl px-4 py-2.5 text-xs font-bold transition-all flex items-center justify-center gap-2 focus:outline-none focus:ring-2 focus:ring-indigo-400 ${
              active
                ? "bg-indigo-500/20 text-indigo-300 border border-indigo-400/30 shadow-lg shadow-indigo-950/40"
                : "text-slate-400 hover:text-slate-100 hover:bg-slate-800"
            }`}
          >
            <Icon className="h-4 w-4" />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
