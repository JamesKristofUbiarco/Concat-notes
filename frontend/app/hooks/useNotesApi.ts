import { useState, useEffect, useCallback } from "react";
import { QueueItem } from "../types";

const API_BASE = "http://localhost:8000";

interface ProcessedWhileAway {
  id: string;
  class_title: string;
  course_name: string;
  processed_at: string | null;
}

export function useNotesApi() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [courses, setCourses] = useState<string[]>([]);
  const [selectedQueueItemId, setSelectedQueueItemId] = useState<string | null>(null);
  const [selectedCourse, setSelectedCourse] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);

  // --- IA Processing ---
  const [isAIProcessing, setIsAIProcessing] = useState(false);
  const [aiStep, setAiStep] = useState(0);

  // --- Notificaciones de procesamiento en segundo plano ---
  const [processedWhileAway, setProcessedWhileAway] = useState<ProcessedWhileAway[]>([]);
  const [showProcessedModal, setShowProcessedModal] = useState(false);

  const fetchNotes = useCallback(async () => {
    try {
      const [resQueue, resArchive, resCourses] = await Promise.all([
        fetch(`${API_BASE}/api/notes/queue`),
        fetch(`${API_BASE}/api/notes/archive`),
        fetch(`${API_BASE}/api/courses`)
      ]);
      if (resQueue.ok && resArchive.ok && resCourses.ok) {
        const queueData = await resQueue.json();
        const archiveData = await resArchive.json();
        const coursesData = await resCourses.json();
        setCourses(coursesData);

        const mapItem = (item: any): QueueItem => ({
          id: item.id,
          writingMode: item.writing_mode || "",
          platform: item.platform || "",
          courseName: item.course_name || "",
          teacher: item.teacher || "",
          courseModule: item.course_module || "",
          classTitle: item.class_title || "",
          transcription: item.transcription || "",
          classSummary: item.class_summary || "",
          myNotes: item.my_notes || "",
          codeSnippets: item.code_snippets || [],
          commandSnippets: item.command_snippets || [],
          status: item.status,
          createdAt: new Date(item.created_at).toLocaleString(),
          structuredMarkdown: item.processed_note?.structured_markdown
        });

        const mergedQueue = [
          ...queueData.map(mapItem),
          ...archiveData.map(mapItem)
        ];
        setQueue(mergedQueue);
      }
    } catch (e) {
      console.error("Error al cargar notas de la API de FastAPI", e);
    }
  }, []);

  // --- Montaje: cargar notas + verificar notificaciones de procesamiento en segundo plano ---
  useEffect(() => {
    setIsMounted(true);
    fetchNotes();

    // Consultar si hay notas procesadas en segundo plano desde la última visita
    const lastVisit = localStorage.getItem("lastVisitTimestamp") || new Date(0).toISOString();
    fetch(`${API_BASE}/api/notes/processed-since?since=${encodeURIComponent(lastVisit)}`)
      .then(res => {
        if (res.ok) return res.json();
        return [];
      })
      .then((data: ProcessedWhileAway[]) => {
        if (data.length > 0) {
          setProcessedWhileAway(data);
          setShowProcessedModal(true);
        }
      })
      .catch(() => {
        // Silenciar errores de red para esta consulta secundaria
      });

    // Actualizar timestamp de última visita
    localStorage.setItem("lastVisitTimestamp", new Date().toISOString());
  }, [fetchNotes]);

  // --- Save to Queue (POST or PUT) ---
  const handleSaveToQueue = useCallback(async (payload: any) => {
    try {
      if (selectedQueueItemId) {
        const response = await fetch(`${API_BASE}/api/notes/${selectedQueueItemId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (response.ok) {
          await fetchNotes();
          const saveBtn = document.getElementById("saveQueueBtn");
          if (saveBtn) {
            saveBtn.classList.add("bg-emerald-600");
            setTimeout(() => saveBtn.classList.remove("bg-emerald-600"), 1000);
          }
        } else {
          console.error("Error al actualizar la nota en el servidor");
        }
      } else {
        const response = await fetch(`${API_BASE}/api/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (response.ok) {
          const createdItem = await response.json();
          await fetchNotes();
          setSelectedQueueItemId(createdItem.id);
          return { openSidebar: true };
        } else {
          console.error("Error al crear la nota en el servidor");
        }
      }
    } catch (e) {
      console.error("Error de red al intentar guardar la nota", e);
    }
    return null;
  }, [selectedQueueItemId, fetchNotes]);

  // --- Delete ---
  const handleDeleteQueueItem = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/notes/${id}`, { method: "DELETE" });
      if (response.ok) {
        await fetchNotes();
        return selectedQueueItemId === id;
      } else {
        console.error("Error al eliminar la nota de la base de datos");
      }
    } catch (e) {
      console.error("Error de red al intentar eliminar la nota", e);
    }
    return false;
  }, [selectedQueueItemId, fetchNotes]);

  // --- AI Processing (Optimizado: 2 pasos de animación en vez de 4) ---
  const handleAIProcess = useCallback(async (
    payload: any,
    setMarkdownResult: (md: string) => void
  ): Promise<void> => {
    setIsAIProcessing(true);
    setAiStep(1);

    let currentId = selectedQueueItemId;
    try {
      if (currentId) {
        await fetch(`${API_BASE}/api/notes/${currentId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      } else {
        const resCreate = await fetch(`${API_BASE}/api/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (resCreate.ok) {
          const created = await resCreate.json();
          currentId = created.id;
          setSelectedQueueItemId(created.id);
        }
      }

      if (!currentId) {
        throw new Error("No se pudo obtener el ID del apunte");
      }

      // Animación simplificada: 2 pasos (contexto → síntesis)
      await new Promise(resolve => setTimeout(resolve, 600));
      setAiStep(2);

      const resProcess = await fetch(`${API_BASE}/api/notes/${currentId}/process`, {
        method: "POST"
      });

      if (resProcess.ok) {
        const processedData = await resProcess.json();
        setMarkdownResult(processedData.structured_markdown);
        await fetchNotes();

        const resultTextArea = document.getElementById("resultArea");
        if (resultTextArea) {
          resultTextArea.classList.add("ring-2", "ring-indigo-500/50");
          setTimeout(() => resultTextArea.classList.remove("ring-2", "ring-indigo-500/50"), 1000);
        }
      } else {
        console.error("Error al procesar la nota en el backend");
      }
    } catch (e) {
      console.error("Error de comunicación con el backend de IA", e);
    } finally {
      setIsAIProcessing(false);
      setAiStep(0);
    }
  }, [selectedQueueItemId, fetchNotes]);

  // --- Load Course MOC ---
  const handleLoadCourse = useCallback(async (
    courseNameParam: string,
    setMarkdownResult: (md: string) => void
  ) => {
    try {
      setSelectedCourse(courseNameParam);
      setSelectedQueueItemId(null);
      const res = await fetch(`${API_BASE}/api/courses/${encodeURIComponent(courseNameParam)}/markdown`);
      if (res.ok) {
        const data = await res.json();
        setMarkdownResult(data.structured_markdown);
        const resultTextArea = document.getElementById("resultArea");
        if (resultTextArea) {
          resultTextArea.classList.add("ring-2", "ring-emerald-500/50");
          setTimeout(() => resultTextArea.classList.remove("ring-2", "ring-emerald-500/50"), 800);
        }
      } else {
        console.error("Error al cargar el curso consolidado");
      }
    } catch (e) {
      console.error("Error de red al intentar cargar el curso", e);
    }
  }, []);

  // --- Load Archive Result ---
  const handleLoadArchiveResult = useCallback((
    item: QueueItem,
    setMarkdownResult: (md: string) => void
  ) => {
    if (item.structuredMarkdown) {
      setSelectedCourse(null);
      setMarkdownResult(item.structuredMarkdown);

      const resultTextArea = document.getElementById("resultArea");
      if (resultTextArea) {
        resultTextArea.classList.add("ring-2", "ring-indigo-500/50");
        setTimeout(() => resultTextArea.classList.remove("ring-2", "ring-indigo-500/50"), 800);
      }
    }
  }, []);

  // --- Reorder Course Notes ---
  const handleReorderCourse = useCallback(async (courseName: string, orderedNoteIds: string[], setMarkdownResult: (md: string) => void) => {
    try {
      const response = await fetch(`${API_BASE}/api/courses/${encodeURIComponent(courseName)}/reorder`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note_ids: orderedNoteIds })
      });
      if (response.ok) {
        await handleLoadCourse(courseName, setMarkdownResult);
      } else {
        console.error("Error al reordenar las clases");
      }
    } catch (e) {
      console.error("Error de red al intentar reordenar", e);
    }
  }, [handleLoadCourse]);

  // Computed values
  const pendingItems = queue.filter(item => item.status === "pending");
  const processedItems = queue.filter(item => item.status === "processed");

  return {
    queue,
    courses,
    selectedQueueItemId,
    setSelectedQueueItemId,
    selectedCourse,
    setSelectedCourse,
    isMounted,
    isAIProcessing,
    aiStep,
    pendingItems,
    processedItems,
    fetchNotes,
    handleSaveToQueue,
    handleDeleteQueueItem,
    handleAIProcess,
    handleLoadCourse,
    handleLoadArchiveResult,
    handleReorderCourse,
    // Notificaciones de procesamiento en segundo plano
    processedWhileAway,
    showProcessedModal,
    setShowProcessedModal,
  };
}
