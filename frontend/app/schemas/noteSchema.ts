import { z } from "zod";

/**
 * Esquema de validación para un snippet de código individual
 */
export const codeSnippetSchema = z.object({
  id: z.string(), // ID único para manejo de listas reactivas en React
  lang: z.string().default(""),
  code: z.string().default(""),
});

/**
 * Esquema de validación para un snippet de comandos individual
 */
export const commandSnippetSchema = z.object({
  id: z.string(), // ID único para manejo de listas reactivas en React
  order: z.string().default(""),
  lang: z.string().default("bash"),
  cmd: z.string().default(""),
});

/**
 * Esquema de validación para un snippet de imagen individual
 */
export const imageSnippetSchema = z.object({
  id: z.string(),
  image_url: z.string(),
  filename: z.string(),
  descripcion_llm: z.string().nullable().optional(),
  image_type: z.string().default("image"),
});

/**
 * Esquema de validación principal para el formulario de Apuntes Crudos
 */
export const noteFormSchema = z.object({
  writingMode: z.string().default(""),
  platform: z.string().default(""),
  courseName: z.string().min(2, {
    message: "El nombre del curso es obligatorio y debe tener al menos 2 caracteres.",
  }),
  teacher: z.string().default(""),
  courseModule: z.string().default(""),
  classTitle: z.string().min(2, {
    message: "El título de la clase es obligatorio y debe tener al menos 2 caracteres.",
  }),
  transcription: z.string().default(""),
  classSummary: z.string().default(""),
  myNotes: z.string().default(""),
  classMinutes: z.string().refine((val) => {
    const num = parseInt(val, 10);
    return !isNaN(num) && num >= 1;
  }, {
    message: "Los minutos de la clase deben ser como mínimo 1."
  }),
  codeSnippets: z.array(codeSnippetSchema).default([]),
  commandSnippets: z.array(commandSnippetSchema).default([]),
  imageSnippets: z.array(imageSnippetSchema).default([]),
  flashcardTarget: z.string().optional().default(""),
});

// Tipos TypeScript inferidos a partir de los esquemas Zod
export type CodeSnippet = z.infer<typeof codeSnippetSchema>;
export type CommandSnippet = z.infer<typeof commandSnippetSchema>;
export type ImageSnippet = z.infer<typeof imageSnippetSchema>;
export type NoteFormData = z.infer<typeof noteFormSchema>;
