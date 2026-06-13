import { CodeSnippet, CommandSnippet, ImageSnippet } from "../schemas/noteSchema";

export interface QueueItem {
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
  classMinutes: number;
  codeSnippets: CodeSnippet[];
  commandSnippets: CommandSnippet[];
  images: ImageSnippet[];
  status: "pending" | "processed" | "failed";
  createdAt: string;
  orderIndex: number;
  structuredMarkdown?: string;
}

export type SidebarTab = "pending" | "processed" | "courses";
