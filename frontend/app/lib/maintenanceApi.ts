export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function maintenanceRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo completar la operación.");
  return data as T;
}

export function jsonRequest(payload: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
}

export interface MaintenanceClass { id: string; course: string; module: string; title: string; status: string; can_regenerate: boolean }
export type Component = "content" | "glossary" | "flashcards";
export const componentLabels: Record<Component, string> = { content: "Contenido", glossary: "Glosario", flashcards: "Flashcards" };
export interface GenerationRequest {
  id: string; phase: string; model: string; model_name: string;
  status: "waiting" | "generating" | "complete" | "timeout" | "error";
  started_at: string; deadline_s: number; first_response_limit_s: number; idle_limit_s: number;
  elapsed_ms: number; input_chars: number; output_chars: number; chunks: number;
  first_event_ms?: number; first_token_ms?: number; last_output_at?: string; last_output_ms?: number;
  timeout_kind?: "total" | "first_response" | "idle";
}
export interface RegenerationJob {
  id: string; status: string; instructions: string; components: Component[]; created_at: string;
  items: { note_id: string; title: string; course: string; status: string; error: string | null;
    phase?: string; phase_started_at?: string;
    metrics?: { evidence_cache_hit?: boolean; evidence_calls?: number; evidence_page?: number;
      evidence_pages?: number; evidence_claims?: number; evidence_format_retries?: number;
      stage_ms?: Record<string, number>; llm_calls?: number; input_tokens?: number; output_tokens?: number;
      llm_requests?: GenerationRequest[];
      flashcards_generated?: number; flashcards_requested?: number; auxiliary_fallback?: boolean;
      retrieval?: { unindexed_prior_notes?: number } };
  }[];
}
