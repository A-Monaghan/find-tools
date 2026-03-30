import { RawEntity, RawRelationship } from "../types";

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? "";

export interface PromptDefaults {
  system_prompt: string;
  user_prompt_template: string;
  content_placeholder: string;
}

export interface AnalyzePayload {
  model_type: "openrouter";
  api_key?: string;
  openrouter_model?: string;
  url?: string;
  text?: string;
  input_mode: "url" | "text";
  system_prompt?: string | null;
  user_prompt_template?: string | null;
}

export interface AnalyzeResponse {
  success: boolean;
  data: { entities: RawEntity[]; relationships: RawRelationship[] };
  extracted_text?: string | null;
}

export interface AnalyzeError {
  detail?: string;
  error?: string;
}

export async function analyzeWithBackend(
  payload: AnalyzePayload
): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const json = await res.json();
  if (!res.ok) {
    const msg =
      (json as AnalyzeError).detail ?? (json as AnalyzeError).error ?? res.statusText;
    throw new Error(msg);
  }
  return json as AnalyzeResponse;
}

export async function fetchPromptDefaults(): Promise<PromptDefaults> {
  const res = await fetch(`${API_BASE}/api/prompt-defaults`);
  if (!res.ok) throw new Error("Failed to load prompt defaults");
  return res.json() as Promise<PromptDefaults>;
}
