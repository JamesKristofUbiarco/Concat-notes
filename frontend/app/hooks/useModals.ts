import { useState, useCallback } from "react";

export function useModals() {
  // --- Modal de Confirmación ---
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMessage, setModalMessage] = useState("");
  const [modalAction, setModalAction] = useState<(() => void) | null>(null);

  const triggerConfirmation = useCallback((message: string, action: () => void) => {
    setModalMessage(message);
    setModalAction(() => action);
    setModalOpen(true);
  }, []);

  const executeModalAction = useCallback(() => {
    if (modalAction) modalAction();
    setModalOpen(false);
  }, [modalAction]);

  const closeModal = useCallback(() => {
    setModalOpen(false);
  }, []);

  // --- Modal de Plantilla ---
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [selectedTemplateCourse, setSelectedTemplateCourse] = useState("");
  const [selectedTemplateModule, setSelectedTemplateModule] = useState("");

  const openTemplateModal = useCallback(() => {
    setTemplateModalOpen(true);
  }, []);

  const closeTemplateModal = useCallback(() => {
    setTemplateModalOpen(false);
  }, []);

  const setTemplateCourse = useCallback((course: string) => {
    setSelectedTemplateCourse(course);
    setSelectedTemplateModule(""); // Reset module when course changes
  }, []);

  return {
    // Confirm modal
    modalOpen,
    modalMessage,
    triggerConfirmation,
    executeModalAction,
    closeModal,
    // Template modal
    templateModalOpen,
    selectedTemplateCourse,
    selectedTemplateModule,
    setSelectedTemplateModule,
    openTemplateModal,
    closeTemplateModal,
    setTemplateCourse,
  };
}
