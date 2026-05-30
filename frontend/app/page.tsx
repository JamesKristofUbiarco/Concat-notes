"use client";

import React, { useState, useEffect } from "react";
import { 
  Sparkles, 
  Layers, 
  Trash2, 
  Eraser, 
  Copy, 
  Check, 
  PlusCircle, 
  Terminal, 
  Code2, 
  AlertTriangle, 
  Cpu, 
  Activity, 
  BookOpen, 
  User, 
  Folder, 
  FileText, 
  MessageSquareCode, 
  FileCode2, 
  Globe, 
  Menu,
  X,
  Plus,
  Save,
  Archive,
  History,
  CornerDownRight,
  ChevronRight,
  ExternalLink,
  RefreshCw
} from "lucide-react";
import { noteFormSchema, NoteFormData, CodeSnippet, CommandSnippet } from "./schemas/noteSchema";

interface QueueItem {
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
  codeSnippets: CodeSnippet[];
  commandSnippets: CommandSnippet[];
  status: "pending" | "processed" | "failed";
  createdAt: string;
  structuredMarkdown?: string;
}

export default function Home() {
  // --- Estados de Formulario Básicos ---
  const [writingMode, setWritingMode] = useState("");
  const [platform, setPlatform] = useState("");
  const [courseName, setCourseName] = useState("");
  const [teacher, setTeacher] = useState("");
  const [courseModule, setCourseModule] = useState("");
  const [classTitle, setClassTitle] = useState("");
  const [transcription, setTranscription] = useState("");
  const [classSummary, setClassSummary] = useState("");
  const [myNotes, setMyNotes] = useState("");

  // --- Estados de Listas Dinámicas ---
  const [codeSnippets, setCodeSnippets] = useState<CodeSnippet[]>([
    { id: "init-code-1", lang: "", code: "" }
  ]);
  const [commandSnippets, setCommandSnippets] = useState<CommandSnippet[]>([
    { id: "init-cmd-1", order: "", lang: "bash", cmd: "" }
  ]);

  // --- Estados de UI, Errores y Copiado ---
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [markdownResult, setMarkdownResult] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "success" | "empty">("idle");

  // --- Estados de Simulación del Agente de IA ---
  const [isAIProcessing, setIsAIProcessing] = useState(false);
  const [aiStep, setAiStep] = useState(0);

  // --- Estados del Modal Personalizado ---
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMessage, setModalMessage] = useState("");
  const [modalAction, setModalAction] = useState<(() => void) | null>(null);

  // --- Estados de la Cola de Notas (Phase 2) ---
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<"pending" | "processed">("pending");
  const [selectedQueueItemId, setSelectedQueueItemId] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);

  // --- Función para cargar datos de la API de FastAPI real ---
  const fetchNotes = async () => {
    try {
      const [resQueue, resArchive] = await Promise.all([
        fetch("http://localhost:8000/api/notes/queue"),
        fetch("http://localhost:8000/api/notes/archive")
      ]);
      if (resQueue.ok && resArchive.ok) {
        const queueData = await resQueue.json();
        const archiveData = await resArchive.json();

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
  };

  // --- Efecto para cargar datos de la base de datos al montar ---
  useEffect(() => {
    setIsMounted(true);
    fetchNotes();
  }, []);

  // --- Handlers de Modales ---
  const triggerConfirmation = (message: string, action: () => void) => {
    setModalMessage(message);
    setModalAction(() => action);
    setModalOpen(true);
  };

  const executeModalAction = () => {
    if (modalAction) modalAction();
    setModalOpen(false);
  };

  // --- Handlers de Snippets de Código ---
  const addCodeSnippet = () => {
    const newSnippet: CodeSnippet = {
      id: `code-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      lang: "",
      code: ""
    };
    setCodeSnippets([...codeSnippets, newSnippet]);
  };

  const removeCodeSnippet = (id: string) => {
    setCodeSnippets(codeSnippets.filter(item => item.id !== id));
  };

  const updateCodeSnippet = (id: string, field: "lang" | "code", value: string) => {
    setCodeSnippets(codeSnippets.map(item => {
      if (item.id === id) {
        return { ...item, [field]: value };
      }
      return item;
    }));
  };

  // --- Handlers de Snippets de Comandos ---
  const addCommandSnippet = () => {
    const newSnippet: CommandSnippet = {
      id: `cmd-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      order: "",
      lang: "bash",
      cmd: ""
    };
    setCommandSnippets([...commandSnippets, newSnippet]);
  };

  const removeCommandSnippet = (id: string) => {
    setCommandSnippets(commandSnippets.filter(item => item.id !== id));
  };

  const updateCommandSnippet = (id: string, field: "order" | "lang" | "cmd", value: string) => {
    setCommandSnippets(commandSnippets.map(item => {
      if (item.id === id) {
        return { ...item, [field]: value };
      }
      return item;
    }));
  };

  // --- Limpieza y Creación Fresh ---
  const resetFormFields = () => {
    setWritingMode("");
    setPlatform("");
    setCourseName("");
    setTeacher("");
    setCourseModule("");
    setClassTitle("");
    setTranscription("");
    setClassSummary("");
    setMyNotes("");
    setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
    setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
    setMarkdownResult("");
    setErrors({});
  };

  const handleNewNote = () => {
    if (selectedQueueItemId) {
      setSelectedQueueItemId(null);
      resetFormFields();
    } else {
      triggerConfirmation(
        "¿Deseas vaciar el formulario actual para crear una nueva ficha desde cero?",
        () => {
          setSelectedQueueItemId(null);
          resetFormFields();
        }
      );
    }
  };

  const handleClearFromModule = () => {
    triggerConfirmation(
      "¿Limpiar desde el módulo de curso? Se conservará Plataforma, Nombre del Curso y Profesor.",
      () => {
        setCourseModule("");
        setClassTitle("");
        setTranscription("");
        setClassSummary("");
        setMyNotes("");
        setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
        setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
        setMarkdownResult("");
        setErrors({});
      }
    );
  };

  const handleClearFromTitle = () => {
    triggerConfirmation(
      "¿Limpiar desde el título de la clase? Se conservará Plataforma, Nombre del Curso, Profesor y Módulo.",
      () => {
        setClassTitle("");
        setTranscription("");
        setClassSummary("");
        setMyNotes("");
        setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
        setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
        setMarkdownResult("");
        setErrors({});
      }
    );
  };

  const handleClearAll = () => {
    triggerConfirmation(
      "¿Estás seguro de que deseas borrar absolutamente todos los campos y snippets?",
      () => {
        setSelectedQueueItemId(null);
        resetFormFields();
      }
    );
  };

  // --- Validación del Formulario mediante Zod ---
  const validateForm = (): NoteFormData | null => {
    const rawData = {
      writingMode,
      platform,
      courseName,
      teacher,
      courseModule,
      classTitle,
      transcription,
      classSummary,
      myNotes,
      codeSnippets: codeSnippets.filter(s => s.code.trim() !== ""),
      commandSnippets: commandSnippets.filter(c => c.cmd.trim() !== ""),
    };

    const result = noteFormSchema.safeParse(rawData);
    if (!result.success) {
      const formattedErrors: Record<string, string> = {};
      result.error.issues.forEach((err) => {
        if (err.path[0]) {
          formattedErrors[err.path[0].toString()] = err.message;
        }
      });
      setErrors(formattedErrors);
      
      const firstErrorKey = Object.keys(formattedErrors)[0];
      const errorElement = document.getElementById(`input-field-${firstErrorKey}`);
      if (errorElement) {
        errorElement.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return null;
    }

    setErrors({});
    return result.data;
  };

  // --- Lógica de Concatenación Local (Manual) ---
  const handleLocalConcatenate = () => {
    const data = validateForm();
    if (!data) return;

    const ticks4 = "`".repeat(4);
    const ticks3 = "`".repeat(3);
    let finalMarkdown = ticks4 + "\n";
    let hasContent = false;

    const addSection = (title: string, content: string) => {
      if (content && content.trim() !== "") {
        finalMarkdown += `### ${title}\n${content.trim()}\n\n`;
        hasContent = true;
      }
    };

    addSection("Modo de redacción", data.writingMode);
    addSection("Plataforma", data.platform);
    addSection("Nombre del curso", data.courseName);
    addSection("Profesor", data.teacher);
    addSection("Módulo del curso", data.courseModule);
    addSection("Título de la clase", data.classTitle);
    addSection("Transcripción", data.transcription);
    addSection("Resumen de la clase", data.classSummary);
    addSection("Notas propias", data.myNotes);

    data.codeSnippets.forEach((snippet) => {
      finalMarkdown += `### Snippet de código\n${ticks3}${snippet.lang}\n${snippet.code}\n${ticks3}\n\n`;
      hasContent = true;
    });

    data.commandSnippets.forEach((snippet) => {
      const orderText = snippet.order ? ` (${snippet.order})` : "";
      finalMarkdown += `### Comando${orderText}\n${ticks3}${snippet.lang}\n${snippet.cmd}\n${ticks3}\n\n`;
      hasContent = true;
    });

    if (hasContent) {
      finalMarkdown = finalMarkdown.replace(/\n\n$/, "\n");
    }
    finalMarkdown += ticks4;

    setMarkdownResult(finalMarkdown);

    // Animación visual de éxito verde
    const resultTextArea = document.getElementById("resultArea");
    if (resultTextArea) {
      resultTextArea.classList.add("ring-2", "ring-emerald-500/50");
      setTimeout(() => resultTextArea.classList.remove("ring-2", "ring-emerald-500/50"), 800);
    }
  };

  // --- GESTIÓN DE LA COLA (Phase 2 CRUD) ---

  // Guardar ficha actual en la cola (Pendiente)
  const handleSaveToQueue = async () => {
    const data = validateForm();
    if (!data) return;

    // Mapear los datos al formato snake_case esperado por el backend
    const payload = {
      writing_mode: writingMode,
      platform,
      course_name: courseName,
      teacher,
      course_module: courseModule,
      class_title: classTitle,
      transcription,
      class_summary: classSummary,
      my_notes: myNotes,
      code_snippets: codeSnippets.filter(s => s.code.trim() !== "").map(s => ({ id: s.id, lang: s.lang, code: s.code })),
      command_snippets: commandSnippets.filter(c => c.cmd.trim() !== "").map(c => ({ id: c.id, order: c.order, lang: c.lang, cmd: c.cmd }))
    };

    try {
      if (selectedQueueItemId) {
        // Actualizar item existente mediante PUT
        const response = await fetch(`http://localhost:8000/api/notes/${selectedQueueItemId}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify(payload)
        });

        if (response.ok) {
          await fetchNotes();
          // Mostrar feedback visual
          const saveBtn = document.getElementById("saveQueueBtn");
          if (saveBtn) {
            saveBtn.classList.add("bg-emerald-600");
            setTimeout(() => saveBtn.classList.remove("bg-emerald-600"), 1000);
          }
        } else {
          console.error("Error al actualizar la nota en el servidor");
        }
      } else {
        // Crear nuevo item pendiente mediante POST
        const response = await fetch("http://localhost:8000/api/notes", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify(payload)
        });

        if (response.ok) {
          const createdItem = await response.json();
          await fetchNotes();
          setSelectedQueueItemId(createdItem.id);
          // Abrir la barra lateral para que el usuario vea que se añadió
          setSidebarOpen(true);
          setSidebarTab("pending");
        } else {
          console.error("Error al crear la nota en el servidor");
        }
      }
    } catch (e) {
      console.error("Error de red al intentar guardar la nota", e);
    }
  };

  // Cargar item de la cola al formulario para editar
  const handleLoadItem = (item: QueueItem) => {
    setSelectedQueueItemId(item.id);
    setWritingMode(item.writingMode);
    setPlatform(item.platform);
    setCourseName(item.courseName);
    setTeacher(item.teacher);
    setCourseModule(item.courseModule);
    setClassTitle(item.classTitle);
    setTranscription(item.transcription);
    setClassSummary(item.classSummary);
    setMyNotes(item.myNotes);
    
    setCodeSnippets(
      item.codeSnippets.length > 0 
        ? item.codeSnippets 
        : [{ id: "init-code-1", lang: "", code: "" }]
    );
    setCommandSnippets(
      item.commandSnippets.length > 0 
        ? item.commandSnippets 
        : [{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]
    );

    if (item.status === "processed" && item.structuredMarkdown) {
      setMarkdownResult(item.structuredMarkdown);
    } else {
      setMarkdownResult("");
    }
    setErrors({});
  };

  // Cargar visualmente el resultado de un archivado en la derecha sin alterar el formulario
  const handleLoadArchiveResult = (item: QueueItem) => {
    if (item.structuredMarkdown) {
      setMarkdownResult(item.structuredMarkdown);
      
      const resultTextArea = document.getElementById("resultArea");
      if (resultTextArea) {
        resultTextArea.classList.add("ring-2", "ring-indigo-500/50");
        setTimeout(() => resultTextArea.classList.remove("ring-2", "ring-indigo-500/50"), 800);
      }
    }
  };

  // Eliminar un item de la cola
  const handleDeleteQueueItem = (id: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Evita cargar el elemento al dar clic en eliminar
    triggerConfirmation(
      "¿Deseas eliminar permanentemente esta ficha de la lista?",
      async () => {
        try {
          const response = await fetch(`http://localhost:8000/api/notes/${id}`, {
            method: "DELETE"
          });
          if (response.ok) {
            await fetchNotes();
            if (selectedQueueItemId === id) {
              setSelectedQueueItemId(null);
              resetFormFields();
            }
          } else {
            console.error("Error al eliminar la nota de la base de datos");
          }
        } catch (e) {
          console.error("Error de red al intentar eliminar la nota", e);
        }
      }
    );
  };

  // --- Lógica de Simulación de Agente IA (LangGraph + Voyage-4 + pgvector) ---
  // --- Lógica del Agente IA Real (FastAPI + pgvector + LangGraph Ready) ---
  const handleAISimulation = async () => {
    const data = validateForm();
    if (!data) return;

    // Mapear los datos al formato snake_case esperado por el backend
    const payload = {
      writing_mode: writingMode,
      platform,
      course_name: courseName,
      teacher,
      course_module: courseModule,
      class_title: classTitle,
      transcription,
      class_summary: classSummary,
      my_notes: myNotes,
      code_snippets: codeSnippets.filter(s => s.code.trim() !== "").map(s => ({ id: s.id, lang: s.lang, code: s.code })),
      command_snippets: commandSnippets.filter(c => c.cmd.trim() !== "").map(c => ({ id: c.id, order: c.order, lang: c.lang, cmd: c.cmd }))
    };

    setIsAIProcessing(true);
    setAiStep(1);

    // 1. Guardar o actualizar la nota primero para asegurar persistencia
    let currentId = selectedQueueItemId;
    try {
      if (currentId) {
        // PUT
        await fetch(`http://localhost:8000/api/notes/${currentId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      } else {
        // POST
        const resCreate = await fetch("http://localhost:8000/api/notes", {
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

      // Animación de Pasos
      // Paso 1: Analizar datos crudos
      await new Promise(resolve => setTimeout(resolve, 800));
      setAiStep(2);

      // Paso 2: Generar embeddings vectoriales (Voyage-4)
      await new Promise(resolve => setTimeout(resolve, 800));
      setAiStep(3);

      // Paso 3: pgvector consulta
      await new Promise(resolve => setTimeout(resolve, 800));
      setAiStep(4);

      // Paso 4: Síntesis LLM en Python
      const resProcess = await fetch(`http://localhost:8000/api/notes/${currentId}/process`, {
        method: "POST"
      });

      if (resProcess.ok) {
        const processedData = await resProcess.json();
        setMarkdownResult(processedData.structured_markdown);
        await fetchNotes();

        // Animación visual de éxito violeta (IA)
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
  };

  // --- Lógica del Portapapeles ---
  const handleCopyClipboard = () => {
    if (!markdownResult || markdownResult === "````\n````") {
      setCopyState("empty");
      setTimeout(() => setCopyState("idle"), 2000);
      return;
    }

    navigator.clipboard.writeText(markdownResult)
      .then(() => {
        setCopyState("success");
        setTimeout(() => setCopyState("idle"), 2000);
      })
      .catch(() => {
        const textarea = document.getElementById("resultArea") as HTMLTextAreaElement;
        if (textarea) {
          textarea.select();
          document.execCommand("copy");
          setCopyState("success");
          setTimeout(() => setCopyState("idle"), 2000);
        }
      });
  };

  // Evitar renderizado de servidor con localStorage incompatibilities
  if (!isMounted) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center font-sans">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-9 h-9 text-indigo-500 animate-spin" />
          <span className="text-sm font-semibold text-slate-400">Cargando Entorno...</span>
        </div>
      </div>
    );
  }

  // Filtrados de cola para el Sidebar
  const pendingItems = queue.filter(item => item.status === "pending");
  const processedItems = queue.filter(item => item.status === "processed");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans transition-colors duration-300 relative overflow-hidden py-8 px-4 md:px-8">
      {/* Luces y brillos radiales decorativos de fondo */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-900/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-900/10 blur-[120px] pointer-events-none" />
      
      <div className="max-w-7xl mx-auto w-full flex-grow flex flex-col z-10">
        
        {/* ENCABEZADO DE LA APLICACIÓN */}
        <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div className="flex items-center gap-3.5">
            {/* Botón de barra lateral (Sidebar Toggle) */}
            <button 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-3 bg-slate-900 hover:bg-slate-800 border border-slate-850 hover:border-slate-700 rounded-xl text-indigo-400 hover:text-indigo-300 transition-all cursor-pointer shadow-md relative"
              title="Cola de apuntes"
            >
              <Menu className="w-6 h-6" />
              {pendingItems.length > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-rose-500 text-white rounded-full flex items-center justify-center text-[10px] font-bold animate-pulse">
                  {pendingItems.length}
                </span>
              )}
            </button>
            <div className="p-3 bg-gradient-to-tr from-blue-600 to-indigo-600 rounded-xl shadow-lg shadow-indigo-500/20 hidden sm:block">
              <Layers className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3.5xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-300 to-violet-400 flex items-center gap-2">
                Concatenador de Apuntes
              </h1>
              <p className="text-slate-400 mt-1 text-xs md:text-sm max-w-xl">
                Cola de notas activa y archivado automático persistente con PostgreSQL y pgvector Docker pre-configurado.
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2 bg-slate-900/80 border border-slate-800 rounded-lg p-1.5 self-start md:self-auto glassmorphism">
            <div className="px-3 py-1.5 rounded-md text-xs font-semibold text-indigo-400 bg-indigo-500/10 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Postgres Submodule Setup
            </div>
            <div className="px-3 py-1.5 rounded-md text-xs font-semibold text-slate-400 flex items-center gap-1.5">
              localStorage Persist
            </div>
          </div>
        </header>

        {/* CONTAINER PRINCIPAL */}
        <main className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-grow relative">
          
          {/* BARRA LATERAL (SIDEBAR DE LA COLA) */}
          <div className={`fixed inset-y-0 left-0 w-80 bg-slate-900 border-r border-slate-800 z-40 transition-transform duration-300 transform glassmorphism shadow-2xl flex flex-col ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}>
            {/* Header del Sidebar */}
            <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-950/60">
              <span className="text-sm font-extrabold text-slate-200 tracking-wider uppercase flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-400" />
                Gestor de Apuntes
              </span>
              <button 
                onClick={() => setSidebarOpen(false)}
                className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition-all cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Selector de pestañas */}
            <div className="grid grid-cols-2 border-b border-slate-800 p-2 bg-slate-950/20">
              <button 
                onClick={() => setSidebarTab("pending")}
                className={`py-2 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer ${
                  sidebarTab === "pending" 
                    ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/20" 
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Archive className="w-3.5 h-3.5" />
                Cola Activa ({pendingItems.length})
              </button>
              <button 
                onClick={() => setSidebarTab("processed")}
                className={`py-2 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer ${
                  sidebarTab === "processed" 
                    ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/20" 
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <History className="w-3.5 h-3.5" />
                Archivados ({processedItems.length})
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
                      onClick={() => handleLoadItem(item)}
                      className={`group border rounded-xl p-3.5 transition-all-custom cursor-pointer flex flex-col gap-2 relative overflow-hidden ${
                        selectedQueueItemId === item.id 
                          ? "bg-indigo-950/20 border-indigo-500/50 glow-indigo" 
                          : "bg-slate-950/40 border-slate-800 hover:border-slate-700/80"
                      }`}
                    >
                      {/* Estado Pildora */}
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
                            onClick={(e) => handleDeleteQueueItem(item.id, e)}
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
              ) : (
                processedItems.length === 0 ? (
                  <div className="text-center py-12 text-slate-500 flex flex-col items-center gap-3">
                    <History className="w-10 h-10 text-slate-700" />
                    <p className="text-xs">El archivo histórico está vacío.</p>
                  </div>
                ) : (
                  processedItems.map((item) => (
                    <div 
                      key={item.id} 
                      onClick={() => handleLoadArchiveResult(item)}
                      className="group bg-slate-950/40 border border-slate-800 hover:border-slate-700/80 rounded-xl p-3.5 transition-all-custom cursor-pointer flex flex-col gap-2 relative"
                    >
                      {/* Estado Pildora */}
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
                              handleLoadItem(item);
                            }}
                            className="p-1 text-blue-400 hover:bg-blue-500/10 rounded text-[9px] font-bold flex items-center gap-0.5"
                          >
                            <ExternalLink className="w-3 h-3" />
                            Editar
                          </button>
                          <button 
                            type="button" 
                            title="Eliminar"
                            onClick={(e) => handleDeleteQueueItem(item.id, e)}
                            className="p-1 text-rose-400 hover:bg-rose-500/10 rounded"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )
              )}
            </div>
            
            {/* Botón inferior nueva ficha */}
            <div className="p-4 border-t border-slate-800 bg-slate-950/40">
              <button 
                onClick={() => {
                  handleNewNote();
                  setSidebarOpen(false);
                }}
                className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs flex justify-center items-center gap-2 cursor-pointer shadow-md transition-all active:scale-[0.98]"
              >
                <Plus className="w-4 h-4" />
                Nueva Ficha
              </button>
            </div>
          </div>

          {/* BACKDROP CUANDO SIDEBAR ESTA ABIERTO (EN PANTALLAS CHICAS) */}
          {sidebarOpen && (
            <div 
              onClick={() => setSidebarOpen(false)}
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs z-30 transition-opacity"
            />
          )}

          {/* SECCIÓN IZQUIERDA: Formulario de Entrada (7 Columnas en LG) */}
          <section className="lg:col-span-7 flex flex-col gap-6 bg-slate-900/40 rounded-2xl p-5 md:p-7 border border-slate-800/80 glassmorphism shadow-2xl relative">
            
            {/* Título de la Sección */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <h2 className="text-md font-bold text-slate-200 tracking-wide uppercase flex items-center gap-2">
                  <span className="w-1.5 h-4 rounded bg-indigo-500" />
                  Ficha Cruda de Entrada
                </h2>
                
                {/* Badge indicador de edición de cola */}
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
                    if (errors.courseName) setErrors(prev => ({ ...prev, courseName: "" }));
                  }}
                  placeholder="Ej. Desarrollo Web Full Stack..." 
                  className={`w-full bg-slate-950/70 border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 transition-all-custom text-slate-300 ${
                    errors.courseName 
                      ? "border-rose-500/80 focus:border-rose-500/90 focus:ring-rose-500/20 ring-1 ring-rose-500/30" 
                      : "border-slate-800 focus:border-indigo-500/60 focus:ring-indigo-500/20"
                  }`}
                />
              </div>

              {/* Grid 2 Columnas: Módulo y Clase */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
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
                      if (errors.classTitle) setErrors(prev => ({ ...prev, classTitle: "" }));
                    }}
                    placeholder="Ej. Introducción a los Hooks..." 
                    className={`w-full bg-slate-950/70 border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 transition-all-custom text-slate-300 ${
                      errors.classTitle 
                        ? "border-rose-500/80 focus:border-rose-500/90 focus:ring-rose-500/20 ring-1 ring-rose-500/30" 
                        : "border-slate-800 focus:border-indigo-500/60 focus:ring-indigo-500/20"
                    }`}
                  />
                </div>
              </div>

              {/* Transcripción de la Clase */}
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

              {/* Resumen de la Clase */}
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

              {/* FRAGMENTOS DE CÓDIGO (Dinámicos) */}
              <div className="border-t border-slate-800/80 pt-6">
                <div className="flex justify-between items-center mb-4">
                  <label className="block text-xs md:text-sm font-semibold text-slate-200 flex items-center gap-2">
                    <Code2 className="w-4 h-4 text-sky-400" />
                    Snippets de código
                  </label>
                  <button 
                    type="button" 
                    onClick={addCodeSnippet}
                    className="text-xs flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 hover:scale-[1.02] font-semibold transition-all"
                  >
                    <PlusCircle className="w-4 h-4" />
                    Añadir otro snippet
                  </button>
                </div>
                
                <div className="flex flex-col gap-4">
                  {codeSnippets.map((snippet, index) => (
                    <div 
                      key={snippet.id} 
                      className="group relative bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 transition-all-custom hover:border-slate-700/60 focus-within:border-indigo-500/40"
                    >
                      <div className="flex justify-between items-center mb-3">
                        <input 
                          type="text" 
                          placeholder="Lenguaje (ej. js, typescript, sql)..." 
                          value={snippet.lang}
                          onChange={(e) => updateCodeSnippet(snippet.id, "lang", e.target.value)}
                          className="w-full md:w-1/3 bg-slate-900 border border-slate-800 rounded-lg text-xs px-3 py-2 text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-all-custom"
                        />
                        {codeSnippets.length > 1 && (
                          <button 
                            type="button" 
                            title="Eliminar snippet" 
                            onClick={() => removeCodeSnippet(snippet.id)}
                            className="p-1.5 text-rose-400/70 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all animate-fade-in"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                      <textarea 
                        rows={4} 
                        placeholder="Pega tu fragmento de código estructurado aquí..."
                        value={snippet.code}
                        onChange={(e) => updateCodeSnippet(snippet.id, "code", e.target.value)}
                        className="w-full bg-slate-950 text-emerald-400 font-mono text-xs md:text-sm border border-slate-900 focus:border-indigo-500/30 rounded-lg px-4 py-3 focus:outline-none focus:ring-1 focus:ring-indigo-500/10 resize-y"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* FRAGMENTOS DE COMANDOS (Dinámicos) */}
              <div className="border-t border-slate-800/80 pt-6">
                <div className="flex justify-between items-center mb-4">
                  <label className="block text-xs md:text-sm font-semibold text-slate-200 flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-amber-400" />
                    Snippets de comandos
                  </label>
                  <button 
                    type="button" 
                    onClick={addCommandSnippet}
                    className="text-xs flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 hover:scale-[1.02] font-semibold transition-all"
                  >
                    <PlusCircle className="w-4 h-4" />
                    Añadir otro comando
                  </button>
                </div>
                
                <div className="flex flex-col gap-4">
                  {commandSnippets.map((snippet, index) => (
                    <div 
                      key={snippet.id} 
                      className="group relative bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 transition-all-custom hover:border-slate-700/60 focus-within:border-indigo-500/40"
                    >
                      <div className="flex justify-between items-start md:items-center gap-3 mb-3">
                        <div className="flex flex-col md:flex-row gap-3 w-full md:w-3/4">
                          <input 
                            type="text" 
                            placeholder="Orden (ej. Paso 1)" 
                            value={snippet.order}
                            onChange={(e) => updateCommandSnippet(snippet.id, "order", e.target.value)}
                            className="w-full md:w-1/2 bg-slate-900 border border-slate-800 rounded-lg text-xs px-3 py-2 text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-all-custom"
                          />
                          <input 
                            type="text" 
                            placeholder="Lenguaje (ej. bash)" 
                            value={snippet.lang}
                            onChange={(e) => updateCommandSnippet(snippet.id, "lang", e.target.value)}
                            className="w-full md:w-1/2 bg-slate-900 border border-slate-800 rounded-lg text-xs px-3 py-2 text-slate-300 focus:outline-none focus:border-indigo-500/50 transition-all-custom"
                          />
                        </div>
                        {commandSnippets.length > 1 && (
                          <button 
                            type="button" 
                            title="Eliminar comando" 
                            onClick={() => removeCommandSnippet(snippet.id)}
                            className="p-1.5 text-rose-400/70 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all animate-fade-in"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                      <textarea 
                        rows={2} 
                        placeholder="Pega tu comando ejecutable de terminal..."
                        value={snippet.cmd}
                        onChange={(e) => updateCommandSnippet(snippet.id, "cmd", e.target.value)}
                        className="w-full bg-slate-950 text-amber-400 font-mono text-xs md:text-sm border border-slate-900 focus:border-indigo-500/30 rounded-lg px-4 py-3 focus:outline-none focus:ring-1 focus:ring-indigo-500/10 resize-y"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* BOTONES DE LIMPIEZA */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 border-t border-slate-800/80 pt-6">
                <button 
                  type="button" 
                  onClick={handleClearFromModule}
                  className="w-full text-xs font-semibold py-3 px-3.5 bg-slate-900 border border-slate-800 hover:border-slate-700/60 hover:bg-slate-850 hover:text-slate-200 text-slate-400 rounded-xl transition-all-custom flex justify-center items-center gap-2 group cursor-pointer"
                >
                  <Eraser className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
                  Desde módulo
                </button>
                <button 
                  type="button" 
                  onClick={handleClearFromTitle}
                  className="w-full text-xs font-semibold py-3 px-3.5 bg-slate-900 border border-slate-800 hover:border-slate-700/60 hover:bg-slate-850 hover:text-slate-200 text-slate-400 rounded-xl transition-all-custom flex justify-center items-center gap-2 group text-center leading-tight cursor-pointer"
                >
                  <Eraser className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
                  Desde Título clase
                </button>
                <button 
                  type="button" 
                  onClick={handleClearAll}
                  className="w-full text-xs font-semibold py-3 px-3.5 bg-rose-950/20 border border-rose-900/30 hover:border-rose-500/40 hover:bg-rose-950/40 text-rose-400 rounded-xl transition-all-custom flex justify-center items-center gap-2 cursor-pointer"
                >
                  <Trash2 className="w-4 h-4" />
                  Borrar todo
                </button>
              </div>

              {/* BOTONES DE GUARDADO Y CONCATENACIÓN */}
              <div className="flex flex-col sm:flex-row gap-4 mt-2">
                
                {/* BOTÓN GUARDAR EN COLA (Phase 2 Addition) */}
                <button 
                  type="button" 
                  id="saveQueueBtn"
                  onClick={handleSaveToQueue}
                  className="flex-1 bg-gradient-to-r from-indigo-700 to-indigo-850 hover:from-indigo-650 hover:to-indigo-800 text-slate-100 font-bold py-3.5 px-6 rounded-xl border border-indigo-500/35 hover:border-indigo-400/50 shadow-lg shadow-indigo-950/25 transition-all-custom flex justify-center items-center gap-2 active:scale-[0.98] cursor-pointer"
                >
                  <Save className="w-5 h-5 text-indigo-300" />
                  {selectedQueueItemId ? "Actualizar en Cola" : "Guardar en Cola"}
                </button>

                <button 
                  type="button" 
                  onClick={handleLocalConcatenate}
                  className="flex-1 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white font-bold py-3.5 px-6 rounded-xl shadow-lg shadow-blue-500/10 hover:shadow-blue-500/20 transition-all-custom flex justify-center items-center gap-2 active:scale-[0.98] cursor-pointer"
                >
                  <Layers className="w-5 h-5" />
                  Concatenar Markdown
                </button>

                {/* BOTÓN PROCESAR CON IA (SIMULADO - MOVERÁ A HISTORIAL) */}
                <button 
                  type="button" 
                  onClick={handleAISimulation}
                  disabled={isAIProcessing}
                  className="flex-1 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-white font-bold py-3.5 px-6 rounded-xl shadow-lg shadow-violet-500/10 hover:shadow-violet-500/20 transition-all-custom flex justify-center items-center gap-2 active:scale-[0.98] cursor-pointer disabled:opacity-50 disabled:pointer-events-none group relative overflow-hidden"
                >
                  <Sparkles className="w-5 h-5 text-violet-200 group-hover:scale-110 transition-transform" />
                  Procesar con Agente IA
                </button>
              </div>

            </div>
          </section>

          {/* SECCIÓN DERECHA: Área de Resultado (5 Columnas en LG) */}
          <section className="lg:col-span-5 flex flex-col bg-slate-900/80 rounded-2xl border border-slate-800 glassmorphism shadow-2xl relative overflow-hidden min-h-[500px]">
            
            {/* Cabecera del Resultado */}
            <div className="bg-slate-900 border-b border-slate-800/80 px-5 py-4 flex justify-between items-center">
              <span className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <FileCode2 className="w-4.5 h-4.5 text-indigo-400" />
                Resultado Estructurado
              </span>
              
              {/* Botón de Copiar */}
              <button 
                type="button" 
                onClick={handleCopyClipboard}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-300 border border-slate-850 cursor-pointer ${
                  copyState === "success" 
                    ? "bg-emerald-500/15 border-emerald-500/35 text-emerald-400" 
                    : copyState === "empty"
                    ? "bg-rose-500/15 border-rose-500/35 text-rose-400"
                    : "bg-slate-950/70 hover:bg-slate-900 text-slate-300 hover:text-slate-100 hover:border-slate-700"
                }`}
              >
                {copyState === "success" ? (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>¡Copiado!</span>
                  </>
                ) : copyState === "empty" ? (
                  <>
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>¡Vacío!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copiar texto</span>
                  </>
                )}
              </button>
            </div>

            {/* AREA DE PROCESAMIENTO ACTIVO (MODO AGENTE IA SIMULADO) */}
            {isAIProcessing && (
              <div className="absolute inset-0 bg-slate-950/90 backdrop-blur-md z-20 flex flex-col items-center justify-center p-6 text-center animate-fade-in">
                <div className="relative mb-6">
                  <div className="w-20 h-20 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center animate-pulse glow-indigo">
                    <Cpu className="w-9 h-9 text-indigo-400 animate-spin" style={{ animationDuration: '6s' }} />
                  </div>
                  <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-indigo-400 to-transparent animate-scanning" />
                </div>

                <h3 className="text-lg font-bold text-slate-200 mb-2">Procesando Apuntes Crudos</h3>
                <p className="text-xs text-slate-400 max-w-sm mb-8 leading-relaxed">
                  El agente LangGraph está estructurando semánticamente las notas y archivándolas automáticamente.
                </p>

                {/* Pasos y Progreso del Flujo de Trabajo */}
                <div className="w-full max-w-xs flex flex-col gap-3.5 text-left border border-slate-800/80 bg-slate-900/60 rounded-xl p-4.5">
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                      aiStep > 1 ? "bg-emerald-500/20 text-emerald-400" : aiStep === 1 ? "bg-indigo-500 text-white animate-pulse" : "bg-slate-800 text-slate-500"
                    }`}>
                      {aiStep > 1 ? "✓" : "1"}
                    </div>
                    <span className={`text-xs font-medium ${aiStep === 1 ? "text-indigo-300 font-semibold" : aiStep > 1 ? "text-slate-400" : "text-slate-600"}`}>
                      Analizando contenido raw...
                    </span>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                      aiStep > 2 ? "bg-emerald-500/20 text-emerald-400" : aiStep === 2 ? "bg-indigo-500 text-white animate-pulse" : "bg-slate-800 text-slate-500"
                    }`}>
                      {aiStep > 2 ? "✓" : "2"}
                    </div>
                    <span className={`text-xs font-medium ${aiStep === 2 ? "text-indigo-300 font-semibold" : aiStep > 2 ? "text-slate-400" : "text-slate-600"}`}>
                      Embeddings semánticos (Voyage-4)...
                    </span>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                      aiStep > 3 ? "bg-emerald-500/20 text-emerald-400" : aiStep === 3 ? "bg-indigo-500 text-white animate-pulse" : "bg-slate-800 text-slate-500"
                    }`}>
                      {aiStep > 3 ? "✓" : "3"}
                    </div>
                    <span className={`text-xs font-medium ${aiStep === 3 ? "text-indigo-300 font-semibold" : aiStep > 3 ? "text-slate-400" : "text-slate-600"}`}>
                      Indexando base en pgvector...
                    </span>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all ${
                      aiStep > 4 ? "bg-emerald-500/20 text-emerald-400" : aiStep === 4 ? "bg-indigo-500 text-white animate-pulse" : "bg-slate-800 text-slate-500"
                    }`}>
                      {aiStep > 4 ? "✓" : "4"}
                    </div>
                    <span className={`text-xs font-medium ${aiStep === 4 ? "text-indigo-300 font-semibold" : aiStep > 4 ? "text-slate-400" : "text-slate-600"}`}>
                      Síntesis de Markdown (LangGraph)...
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* ÁREA DE RESULTADO (SOLO LECTURA) */}
            <div className="flex-grow p-5 relative flex flex-col">
              <textarea 
                id="resultArea"
                readOnly 
                value={markdownResult}
                placeholder="Ingresa datos crudos a la izquierda y presiona 'Concatenar' o 'Procesar con IA' para estructurar notas. O carga un archivado desde la barra de cola lateral..."
                className="w-full flex-grow bg-transparent text-slate-300 font-mono text-xs md:text-sm outline-none resize-none scrollbar-thin whitespace-pre-wrap leading-relaxed focus:ring-0"
              />
            </div>

            {/* Footer Informativo del Agente */}
            <div className="bg-slate-950/80 border-t border-slate-800/80 px-5 py-3.5 flex justify-between items-center text-[11px] text-slate-500">
              <span className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-indigo-500" />
                PostgreSQL + pgvector Submodule Pre-set
              </span>
              <span>Markdown Standard</span>
            </div>
          </section>

        </main>
      </div>

      {/* MODAL DE CONFIRMACIÓN PERSONALIZADO */}
      {modalOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 max-w-sm w-full transition-transform transform scale-100 glow-indigo">
            <h3 className="text-md font-bold text-slate-200 mb-3.5 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Confirmar acción
            </h3>
            
            <p className="text-slate-400 mb-6 text-xs md:text-sm leading-relaxed">
              {modalMessage}
            </p>
            
            <div className="flex justify-end gap-3">
              <button 
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:bg-slate-900 hover:text-slate-200 text-slate-400 rounded-lg text-xs font-semibold transition-all cursor-pointer"
              >
                Cancelar
              </button>
              <button 
                onClick={executeModalAction}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer"
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
