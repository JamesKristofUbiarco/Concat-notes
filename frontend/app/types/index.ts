import { CodeSnippet, CommandSnippet } from "../schemas/noteSchema";

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
  codeSnippets: CodeSnippet[];
  commandSnippets: CommandSnippet[];
  status: "pending" | "processed" | "failed";
  createdAt: string;
  orderIndex: number;
  structuredMarkdown?: string;
}

export type SidebarTab = "pending" | "processed" | "courses";
