import type { RunDetail, RunSummary, StartRunPayload } from "./types";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new Error(`Cannot reach the engine at ${BASE}. Is the API running (uvicorn engine.api:app)?`);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function apiBase(): string {
  return BASE;
}

export function health() {
  return request<{ status: string; provider: string; model: string; provider_error: string | null; outputs: string[] }>(
    "/health",
  );
}

export function startRunWithFiles(files: File[], payload: StartRunPayload) {
  const form = new FormData();
  form.append("payload", JSON.stringify(payload));
  files.forEach((file) => form.append("files", file, file.name));
  return request<{ thread_id: string; status: string; label: string }>("/run/upload", { method: "POST", body: form });
}

export function startRun(payload: StartRunPayload) {
  return request<{ thread_id: string; status: string; label: string }>("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getRun(threadId: string) {
  return request<RunDetail>(`/run/${threadId}`);
}

export function resumeRun(
  threadId: string,
  decision: { action: "accept" | "refine"; instruction?: string; types?: string[] },
) {
  return request<{ thread_id: string; status: string; action: string }>(`/run/${threadId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(decision),
  });
}

export function listRuns() {
  return request<RunSummary[]>("/runs");
}

export function downloadUrl(threadId: string, artefactType: string, ext?: string) {
  return `${BASE}/run/${threadId}/artefacts/${artefactType}/download${ext ? `?ext=${ext}` : ""}`;
}

/**
 * Render an artefact on the fly for preview. Unlike downloadUrl this works at any
 * stage, including while the run is paused for review — nothing is written to
 * disk, so an operator can inspect the real output before approving it.
 */
export function previewUrl(threadId: string, artefactType: string, ext?: string) {
  return `${BASE}/run/${threadId}/preview/${artefactType}${ext ? `?ext=${ext}` : ""}`;
}

export interface TemplateOption {
  key: string;
  label: string;
  blurb: string;
  cover: string;
  cover_accent: string;
  cover_sub: string;
  slide: string;
  ink: string;
  accent: string;
  note: string;
  top_bar: boolean;
  preview: string;
}

/**
 * Design templates. The API also returns each template's palette, but the
 * rendered `preview` image is what actually shows the operator what they get.
 */
export function listTemplates() {
  return request<{ default: string; templates: TemplateOption[] }>("/templates");
}

export function templatePreviewUrl(previewPath: string) {
  return `${BASE}${previewPath}`;
}

export interface LanguageOption {
  code: string;
  label: string;
  latin: boolean;
}

/**
 * Languages an artefact can be written in, plus which artefacts have a PDF or
 * PNG deliverable that cannot draw non-Latin scripts.
 */
export function listLanguages() {
  return request<{
    languages: LanguageOption[];
    script_limited_artefacts: string[];
    note: string;
  }>("/languages");
}
