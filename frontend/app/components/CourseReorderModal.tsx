import React, { useState, useEffect } from "react";
import { X, Save, GripVertical } from "lucide-react";
import { QueueItem } from "../types";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

interface CourseReorderModalProps {
  isOpen: boolean;
  courseName: string | null;
  notes: QueueItem[];
  onClose: () => void;
  onSave: (courseName: string, orderedNoteIds: string[]) => Promise<void>;
}

// Subcomponente individual ordenable
function SortableItem({ item }: { item: QueueItem }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 p-3 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 rounded-lg group"
    >
      <div
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing p-1 text-slate-500 hover:text-slate-300"
      >
        <GripVertical className="w-5 h-5" />
      </div>
      <div className="flex-1 flex flex-col">
        <span className="text-sm font-bold text-slate-200">{item.classTitle}</span>
        <span className="text-xs text-slate-400">{item.createdAt.split(",")[0]}</span>
      </div>
    </div>
  );
}

export function CourseReorderModal({ isOpen, courseName, notes, onClose, onSave }: CourseReorderModalProps) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setItems([...notes]);
    }
  }, [isOpen, notes]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setItems((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id);
        const newIndex = items.findIndex((item) => item.id === over.id);
        return arrayMove(items, oldIndex, newIndex);
      });
    }
  };

  const handleSave = async () => {
    if (!courseName) return;
    setIsSaving(true);
    try {
      const ids = items.map((i) => i.id);
      await onSave(courseName, ids);
      onClose();
    } catch (error) {
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen || !courseName) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />
      
      {/* Modal */}
      <div className="relative bg-slate-900 border border-slate-700 shadow-2xl rounded-2xl w-full max-w-lg flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="p-5 border-b border-slate-800 flex justify-between items-center bg-slate-950/50">
          <div>
            <h2 className="text-lg font-bold text-slate-200 flex items-center gap-2">
              Reordenar Clases
            </h2>
            <p className="text-xs text-slate-400 mt-1 uppercase tracking-wide">
              {courseName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto max-h-[60vh] scrollbar-thin">
          <p className="text-sm text-slate-400 mb-4">
            Arrastra las tarjetas para ajustar el orden en que se concatenarán en el documento final.
          </p>
          
          <DndContext 
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext 
              items={items.map((i) => i.id)}
              strategy={verticalListSortingStrategy}
            >
              <div className="flex flex-col gap-2">
                {items.map((item) => (
                  <SortableItem key={item.id} item={item} />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </div>

        <div className="p-5 border-t border-slate-800 bg-slate-950/50 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors shadow-lg shadow-indigo-500/20 disabled:opacity-50"
          >
            {isSaving ? "Guardando..." : (
              <>
                <Save className="w-4 h-4" />
                Guardar Orden
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
