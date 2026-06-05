"use client";

import React, { useState, useCallback } from "react";
import { Layers, Menu, RefreshCw } from "lucide-react";
import { SidebarTab } from "./types";
import { useModals } from "./hooks/useModals";
import { useNoteForm } from "./hooks/useNoteForm";
import { useNotesApi } from "./hooks/useNotesApi";
import { Sidebar } from "./components/Sidebar";
import { NoteForm } from "./components/NoteForm";
import { ResultPanel } from "./components/ResultPanel";
import { ConfirmModal } from "./components/ConfirmModal";
import { TemplateModal } from "./components/TemplateModal";
import { ProcessedNotesModal } from "./components/ProcessedNotesModal";
import { CourseReorderModal } from "./components/CourseReorderModal";

export default function Home() {
  const modals = useModals();
  const form = useNoteForm(modals.triggerConfirmation);
  const api = useNotesApi();

  // --- UI State ---
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("pending");
  const [copyState, setCopyState] = useState<"idle" | "success" | "empty">("idle");
  const [isReorderModalOpen, setIsReorderModalOpen] = useState(false);

  // --- Derived data for template modal ---
  const uniqueCoursesForTemplate = Array.from(new Set(api.queue.map(item => item.courseName).filter(Boolean)));
  const uniqueModulesForTemplate = modals.selectedTemplateCourse
    ? Array.from(new Set(api.queue.filter(item => item.courseName === modals.selectedTemplateCourse).map(item => item.courseModule).filter(Boolean)))
    : [];

  // --- Orchestrated Handlers ---
  const handleNewNote = useCallback(() => {
    if (api.selectedQueueItemId) {
      api.setSelectedQueueItemId(null);
      form.resetFormFields();
    } else {
      modals.triggerConfirmation(
        "¿Deseas vaciar el formulario actual para crear una nueva ficha desde cero?",
        () => {
          api.setSelectedQueueItemId(null);
          form.resetFormFields();
        }
      );
    }
    setSidebarOpen(false);
  }, [api.selectedQueueItemId, api, form, modals]);

  const handleLoadItem = useCallback((item: typeof api.queue[0]) => {
    api.setSelectedQueueItemId(item.id);
    api.setSelectedCourse(null);
    form.loadFromItem(item);
  }, [api, form]);

  const handleLoadArchiveResult = useCallback((item: typeof api.queue[0]) => {
    api.handleLoadArchiveResult(item, form.setMarkdownResult);
  }, [api, form.setMarkdownResult]);

  const handleLoadCourse = useCallback((courseName: string) => {
    api.handleLoadCourse(courseName, form.setMarkdownResult);
  }, [api, form.setMarkdownResult]);

  const handleDeleteItem = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    modals.triggerConfirmation(
      "¿Deseas eliminar permanentemente esta ficha de la lista?",
      async () => {
        const wasSelected = await api.handleDeleteQueueItem(id);
        if (wasSelected) {
          api.setSelectedQueueItemId(null);
          form.resetFormFields();
        }
      }
    );
  }, [modals, api, form]);

  const handleSaveToQueue = useCallback(async () => {
    const data = form.validateForm();
    if (!data) return;
    const result = await api.handleSaveToQueue(form.buildPayload());
    if (result?.openSidebar) {
      setSidebarOpen(true);
      setSidebarTab("pending");
    }
  }, [form, api]);

  const handleAIProcess = useCallback(async () => {
    const data = form.validateForm();
    if (!data) return;
    await api.handleAIProcess(form.buildPayload(), form.setMarkdownResult);
  }, [form, api]);

  const handleClearAll = useCallback(() => {
    form.handleClearAll(() => api.setSelectedQueueItemId(null));
  }, [form, api]);

  const handleCreateFromTemplate = useCallback(() => {
    if (!modals.selectedTemplateCourse) return;
    const templateItem = api.queue.find(item => item.courseName === modals.selectedTemplateCourse);
    if (templateItem) {
      form.loadFromTemplate(templateItem, modals.selectedTemplateModule || undefined);
      api.setSelectedQueueItemId(null);
      api.setSelectedCourse(null);
      setSidebarOpen(false);
    }
    modals.closeTemplateModal();
  }, [modals, api, form]);

  const handleCopyClipboard = useCallback(() => {
    if (!form.markdownResult || form.markdownResult === "````\n````") {
      setCopyState("empty");
      setTimeout(() => setCopyState("idle"), 2000);
      return;
    }
    navigator.clipboard.writeText(form.markdownResult)
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
  }, [form.markdownResult]);

  // --- Loading state ---
  if (!api.isMounted) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center font-sans">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-9 h-9 text-indigo-500 animate-spin" />
          <span className="text-sm font-semibold text-slate-400">Cargando Entorno...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans transition-colors duration-300 relative overflow-hidden py-8 px-4 md:px-8">
      {/* Luces decorativas de fondo */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-900/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-900/10 blur-[120px] pointer-events-none" />
      
      <div className="max-w-7xl mx-auto w-full flex-grow flex flex-col z-10">
        
        {/* HEADER */}
        <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div className="flex items-center gap-3.5">
            <button 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-3 bg-slate-900 hover:bg-slate-800 border border-slate-850 hover:border-slate-700 rounded-xl text-indigo-400 hover:text-indigo-300 transition-all cursor-pointer shadow-md relative"
              title="Cola de apuntes"
            >
              <Menu className="w-6 h-6" />
              {api.pendingItems.length > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-rose-500 text-white rounded-full flex items-center justify-center text-[10px] font-bold animate-pulse">
                  {api.pendingItems.length}
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

        {/* MAIN CONTENT */}
        <main className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-grow relative">
          
          <Sidebar
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
            sidebarTab={sidebarTab}
            onTabChange={setSidebarTab}
            pendingItems={api.pendingItems}
            processedItems={api.processedItems}
            courses={api.courses}
            selectedQueueItemId={api.selectedQueueItemId}
            selectedCourse={api.selectedCourse}
            onLoadItem={handleLoadItem}
            onLoadArchiveResult={handleLoadArchiveResult}
            onLoadCourse={handleLoadCourse}
            onDeleteItem={handleDeleteItem}
            onNewNote={handleNewNote}
            onOpenTemplateModal={modals.openTemplateModal}
            onOpenReorderModal={() => setIsReorderModalOpen(true)}
          />

          <NoteForm
            {...form}
            selectedQueueItemId={api.selectedQueueItemId}
            isAIProcessing={api.isAIProcessing}
            onSaveToQueue={handleSaveToQueue}
            onConcatenate={form.handleLocalConcatenate}
            onAIProcess={handleAIProcess}
            onClearFromModule={form.handleClearFromModule}
            onClearFromTitle={form.handleClearFromTitle}
            onClearAll={handleClearAll}
          />

          <ResultPanel
            markdownResult={form.markdownResult}
            copyState={copyState}
            onCopy={handleCopyClipboard}
            isAIProcessing={api.isAIProcessing}
            aiStep={api.aiStep}
          />
        </main>
      </div>

      {/* MODALS */}
      <ProcessedNotesModal
        isOpen={api.showProcessedModal}
        notes={api.processedWhileAway}
        onClose={() => api.setShowProcessedModal(false)}
        onSelectNote={(noteId: string) => {
          const item = api.processedItems.find(q => q.id === noteId);
          if (item) handleLoadArchiveResult(item);
          api.setShowProcessedModal(false);
        }}
      />

      <TemplateModal
        isOpen={modals.templateModalOpen}
        courses={uniqueCoursesForTemplate}
        modules={uniqueModulesForTemplate}
        selectedCourse={modals.selectedTemplateCourse}
        selectedModule={modals.selectedTemplateModule}
        onCourseChange={modals.setTemplateCourse}
        onModuleChange={modals.setSelectedTemplateModule}
        onCreate={handleCreateFromTemplate}
        onClose={modals.closeTemplateModal}
      />

      <ConfirmModal
        isOpen={modals.modalOpen}
        message={modals.modalMessage}
        onConfirm={modals.executeModalAction}
        onCancel={modals.closeModal}
      />

      <CourseReorderModal
        isOpen={isReorderModalOpen}
        courseName={api.selectedCourse}
        notes={api.processedItems.filter(item => item.courseName === api.selectedCourse)}
        onClose={() => setIsReorderModalOpen(false)}
        onSave={(courseName, ids) => api.handleReorderCourse(courseName, ids, form.setMarkdownResult)}
      />
    </div>
  );
}
