import React from "react";
import { AlertTriangle } from "lucide-react";

interface ConfirmModalProps {
  isOpen: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({ isOpen, message, onConfirm, onCancel }: ConfirmModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 max-w-sm w-full transition-transform transform scale-100 glow-indigo">
        <h3 className="text-md font-bold text-slate-200 mb-3.5 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-500" />
          Confirmar acción
        </h3>
        
        <p className="text-slate-400 mb-6 text-xs md:text-sm leading-relaxed">
          {message}
        </p>
        
        <div className="flex justify-end gap-3">
          <button 
            onClick={onCancel}
            className="px-4 py-2 bg-slate-950 border border-slate-800 hover:bg-slate-900 hover:text-slate-200 text-slate-400 rounded-lg text-xs font-semibold transition-all cursor-pointer"
          >
            Cancelar
          </button>
          <button 
            onClick={onConfirm}
            className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer"
          >
            Confirmar
          </button>
        </div>
      </div>
    </div>
  );
}
