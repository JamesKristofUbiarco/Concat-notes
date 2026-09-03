export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Lane = "left" | "right";
export type BlockType =
  | "question" | "concept" | "paragraph" | "heading" | "bullet_list" | "numbered_list"
  | "procedure" | "code" | "code_output" | "command" | "image" | "table" | "formula"
  | "mermaid" | "quote" | "warning" | "callout" | "resource" | "quiz"
  | "project_goal" | "summary" | "markdown";

export interface NoteSection { id: string; title: string; order: number }
export interface NoteBlock {
  id: string;
  section_id: string;
  type: BlockType;
  lane: Lane;
  reading_order: number;
  content: string | string[] | Record<string, unknown>;
  layout: { gap_before?: number; [key: string]: unknown };
  sources: Array<Record<string, unknown>>;
  asset?: Record<string, unknown> | null;
}
export interface NoteRelation {
  id: string;
  from_block_id: string;
  to_block_id: string;
  type: string;
  order: number;
}
export interface NoteDocumentData {
  schema_version: "1.0";
  document_id: string;
  origin: Record<string, unknown>;
  metadata: Record<string, unknown>;
  composition: Record<string, unknown>;
  sections: NoteSection[];
  blocks: NoteBlock[];
  relations: NoteRelation[];
}
export interface StructuredNote {
  id: string;
  raw_note_id: string | null;
  collection_id: string | null;
  origin_kind: string;
  migration_status: string;
  current_revision_id: string;
  revision_number: number;
  title: string;
  course_name: string;
  tags: string[];
  document: NoteDocumentData;
  rendered_markdown: string;
  created_at: string;
  updated_at: string;
}
export interface NoteOperation {
  op: string;
  target_id?: string;
  value?: unknown;
  block?: Partial<NoteBlock>;
  section?: Partial<NoteSection>;
  relation?: Partial<NoteRelation>;
}
export interface PatchProposal {
  id: string;
  base_revision_id: string;
  status: string;
  intent: string;
  summary: string;
  operations: NoteOperation[];
  validation: { affected_blocks?: string[]; rendered_preview?: string; [key: string]: unknown };
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "No se pudo completar la operación.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function blockText(block: NoteBlock): string {
  if (typeof block.content === "string") return block.content;
  if (Array.isArray(block.content)) return block.content.join("\n");
  return String(block.content.text ?? block.content.code ?? "");
}
