import { useState, useCallback } from "react";
import { noteFormSchema, NoteFormData, CodeSnippet, CommandSnippet, ImageSnippet } from "../schemas/noteSchema";
import { QueueItem } from "../types";

export function useNoteForm(triggerConfirmation: (msg: string, action: () => void) => void) {
  // --- Estados de Formulario ---
  const [writingMode, setWritingMode] = useState("");
  const [platform, setPlatform] = useState("");
  const [courseName, setCourseName] = useState("");
  const [teacher, setTeacher] = useState("");
  const [courseModule, setCourseModule] = useState("");
  const [classTitle, setClassTitle] = useState("");
  const [transcription, setTranscription] = useState("");
  const [classSummary, setClassSummary] = useState("");
  const [myNotes, setMyNotes] = useState("");
  const [classMinutes, setClassMinutes] = useState("");

  const [codeSnippets, setCodeSnippets] = useState<CodeSnippet[]>([
    { id: "init-code-1", lang: "", code: "" }
  ]);
  const [commandSnippets, setCommandSnippets] = useState<CommandSnippet[]>([
    { id: "init-cmd-1", order: "", lang: "bash", cmd: "" }
  ]);

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [markdownResult, setMarkdownResult] = useState("");
  const [imageSnippets, setImageSnippets] = useState<ImageSnippet[]>([]);

  // --- Handlers de Snippets de Imagen ---
  const addImageSnippet = useCallback((newImg: ImageSnippet) => {
    setImageSnippets(prev => [...prev, newImg]);
  }, []);

  const removeImageSnippet = useCallback((id: string) => {
    setImageSnippets(prev => prev.filter(item => item.id !== id));
  }, []);

  const updateImageSnippetDescription = useCallback((id: string, value: string) => {
    setImageSnippets(prev => prev.map(item => item.id === id ? { ...item, descripcion_llm: value } : item));
  }, []);

  // --- Handlers de Snippets de Código ---
  const addCodeSnippet = useCallback(() => {
    const newSnippet: CodeSnippet = {
      id: `code-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      lang: "",
      code: ""
    };
    setCodeSnippets(prev => [...prev, newSnippet]);
  }, []);

  const removeCodeSnippet = useCallback((id: string) => {
    setCodeSnippets(prev => prev.filter(item => item.id !== id));
  }, []);

  const updateCodeSnippet = useCallback((id: string, field: "lang" | "code", value: string) => {
    setCodeSnippets(prev => prev.map(item => item.id === id ? { ...item, [field]: value } : item));
  }, []);

  // --- Handlers de Snippets de Comandos ---
  const addCommandSnippet = useCallback(() => {
    const newSnippet: CommandSnippet = {
      id: `cmd-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      order: "",
      lang: "bash",
      cmd: ""
    };
    setCommandSnippets(prev => [...prev, newSnippet]);
  }, []);

  const removeCommandSnippet = useCallback((id: string) => {
    setCommandSnippets(prev => prev.filter(item => item.id !== id));
  }, []);

  const updateCommandSnippet = useCallback((id: string, field: "order" | "lang" | "cmd", value: string) => {
    setCommandSnippets(prev => prev.map(item => item.id === id ? { ...item, [field]: value } : item));
  }, []);

  // --- Reset / Clear ---
  const resetFormFields = useCallback(() => {
    setWritingMode("");
    setPlatform("");
    setCourseName("");
    setTeacher("");
    setCourseModule("");
    setClassTitle("");
    setTranscription("");
    setClassSummary("");
    setMyNotes("");
    setClassMinutes("");
    setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
    setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
    setImageSnippets([]);
    setMarkdownResult("");
    setErrors({});
  }, []);

  const handleClearFromModule = useCallback(() => {
    triggerConfirmation(
      "¿Limpiar desde el módulo de curso? Se conservará Plataforma, Nombre del Curso y Profesor.",
      () => {
        setCourseModule("");
        setClassTitle("");
        setTranscription("");
        setClassSummary("");
        setMyNotes("");
        setClassMinutes("");
        setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
        setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
        setImageSnippets([]);
        setMarkdownResult("");
        setErrors({});
      }
    );
  }, [triggerConfirmation]);

  const handleClearFromTitle = useCallback(() => {
    triggerConfirmation(
      "¿Limpiar desde el título de la clase? Se conservará Plataforma, Nombre del Curso, Profesor y Módulo.",
      () => {
        setClassTitle("");
        setTranscription("");
        setClassSummary("");
        setMyNotes("");
        setClassMinutes("");
        setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
        setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
        setImageSnippets([]);
        setMarkdownResult("");
        setErrors({});
      }
    );
  }, [triggerConfirmation]);

  const handleClearAll = useCallback((clearIdCallback: () => void) => {
    triggerConfirmation(
      "¿Estás seguro de que deseas borrar absolutamente todos los campos y snippets?",
      () => {
        clearIdCallback();
        resetFormFields();
      }
    );
  }, [triggerConfirmation, resetFormFields]);

  // --- Validación ---
  const validateForm = useCallback((): NoteFormData | null => {
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
      classMinutes,
      codeSnippets: codeSnippets.filter(s => s.code.trim() !== ""),
      commandSnippets: commandSnippets.filter(c => c.cmd.trim() !== ""),
      imageSnippets,
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
  }, [writingMode, platform, courseName, teacher, courseModule, classTitle, transcription, classSummary, myNotes, classMinutes, codeSnippets, commandSnippets, imageSnippets]);

  // --- Concatenación Local ---
  const handleLocalConcatenate = useCallback(() => {
    const data = validateForm();
    if (!data) return;

    const ticks3 = "`".repeat(3);
    let finalMarkdown = "";
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
      finalMarkdown = finalMarkdown.trim();
    }

    setMarkdownResult(finalMarkdown);

    // Animación visual de éxito verde
    const resultTextArea = document.getElementById("resultArea");
    if (resultTextArea) {
      resultTextArea.classList.add("ring-2", "ring-emerald-500/50");
      setTimeout(() => resultTextArea.classList.remove("ring-2", "ring-emerald-500/50"), 800);
    }
  }, [validateForm]);

  // --- Cargar item de la cola al formulario ---
  const loadFromItem = useCallback((item: QueueItem) => {
    setWritingMode(item.writingMode);
    setPlatform(item.platform);
    setCourseName(item.courseName);
    setTeacher(item.teacher);
    setCourseModule(item.courseModule);
    setClassTitle(item.classTitle);
    setTranscription(item.transcription);
    setClassSummary(item.classSummary);
    setMyNotes(item.myNotes);
    setClassMinutes(item.classMinutes ? item.classMinutes.toString() : "");

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
    setImageSnippets(item.images || []);

    if (item.status === "processed" && item.structuredMarkdown) {
      setMarkdownResult(item.structuredMarkdown);
    } else {
      setMarkdownResult("");
    }
    setErrors({});
  }, []);

  // --- Cargar desde plantilla de curso ---
  const loadFromTemplate = useCallback((templateItem: QueueItem, moduleOverride?: string) => {
    setWritingMode(templateItem.writingMode);
    setPlatform(templateItem.platform);
    setCourseName(templateItem.courseName);
    setTeacher(templateItem.teacher);
    setCourseModule(moduleOverride || templateItem.courseModule);

    setClassTitle("");
    setTranscription("");
    setClassSummary("");
    setMyNotes("");
    setClassMinutes("");
    setCodeSnippets([{ id: "init-code-1", lang: "", code: "" }]);
    setCommandSnippets([{ id: "init-cmd-1", order: "", lang: "bash", cmd: "" }]);
    setImageSnippets([]);
    setMarkdownResult("");
    setErrors({});
  }, []);

  // --- Build payload for API ---
  const buildPayload = useCallback(() => ({
    writing_mode: writingMode,
    platform,
    course_name: courseName,
    teacher,
    course_module: courseModule,
    class_title: classTitle,
    transcription,
    class_summary: classSummary,
    my_notes: myNotes,
    class_minutes: parseInt(classMinutes, 10) || 0,
    code_snippets: codeSnippets.filter(s => s.code.trim() !== "").map(s => ({ id: s.id, lang: s.lang, code: s.code })),
    command_snippets: commandSnippets.filter(c => c.cmd.trim() !== "").map(c => ({ id: c.id, order: c.order, lang: c.lang, cmd: c.cmd })),
    image_snippets: imageSnippets.map(img => ({
      id: img.id,
      image_url: img.image_url,
      filename: img.filename,
      descripcion_llm: img.descripcion_llm,
      image_type: img.image_type || "image"
    })),
  }), [writingMode, platform, courseName, teacher, courseModule, classTitle, transcription, classSummary, myNotes, classMinutes, codeSnippets, commandSnippets, imageSnippets]);

  return {
    // Form values
    writingMode, setWritingMode,
    platform, setPlatform,
    courseName, setCourseName,
    teacher, setTeacher,
    courseModule, setCourseModule,
    classTitle, setClassTitle,
    transcription, setTranscription,
    classSummary, setClassSummary,
    myNotes, setMyNotes,
    classMinutes, setClassMinutes,
    codeSnippets, commandSnippets, imageSnippets,
    errors, setErrors,
    markdownResult, setMarkdownResult,
    // Snippet handlers
    addCodeSnippet, removeCodeSnippet, updateCodeSnippet,
    addCommandSnippet, removeCommandSnippet, updateCommandSnippet,
    addImageSnippet, removeImageSnippet, updateImageSnippetDescription, setImageSnippets,
    // Actions
    resetFormFields,
    handleClearFromModule,
    handleClearFromTitle,
    handleClearAll,
    validateForm,
    handleLocalConcatenate,
    loadFromItem,
    loadFromTemplate,
    buildPayload,
  };
}
