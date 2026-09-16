export type ArtefactType =
  | "advisory"
  | "executive_summary"
  | "linkedin_post"
  | "x_thread"
  | "presentation"
  | "video_package"
  | "infographic";

export type RunStatus = "running" | "awaiting_review" | "complete" | "failed";

export interface FactCheckVerdict {
  claim: string;
  verdict: string;
  citation: string | null;
}

export interface FactCheck {
  verdicts: FactCheckVerdict[];
  meta: {
    sentences_checked?: number;
    sentences_supported?: number;
    sentences_unsupported?: number;
    support_ratio?: number;
    unverified_iocs?: string[];
    regenerated_for_grounding?: boolean;
    missing_fields?: string[];
    retries?: number;
  };
}

export type Draft = Record<string, unknown>;

export interface ExportedFile {
  type: string;
  ext: string;
  path: string;
  bytes: number;
  sha256: string;
}

export interface ExportManifest {
  status: string;
  run_id: string;
  artefacts: { type: string; valid: boolean; missing_fields: string[]; sha256: string }[];
  files: ExportedFile[];
  render_error: string | null;
  source: string | null;
  sources: string[];
  model: string | null;
}

export interface ContentModel {
  title?: string;
  severity?: string;
  source_type?: string;
  language?: string;
  facts?: { text: string; source_ref: string }[];
  iocs?: string[];
  timeline?: string[];
  entities?: string[];
  key_messages?: string[];
  recommended_actions?: string[];
}

export interface SourceDescriptor {
  source_id: string;
  kind: string;
  source_type: string;
  language: string;
  blocks: number;
}

export interface RunSummary {
  thread_id: string;
  label: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  artefact_types: string[];
  title: string;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  content_model: ContentModel;
  artefacts: Record<string, Draft>;
  fact_checks: Record<string, FactCheck>;
  export: ExportManifest | null;
  review: { action?: string; instruction?: string; types?: string[] } | null;
  review_request: { content_model?: ContentModel } | null;
  sources: SourceDescriptor[];
  warnings: string[];
}

export interface RunParams {
  target_audience?: string;
  tone?: string;
  language?: string;
  level_of_detail?: string;
}

export interface StartRunPayload {
  sources?: { id?: string; kind?: string; text?: string; url?: string }[];
  selected_outputs: string[];
  params?: RunParams;
  label?: string;
}

export const ARTEFACT_TYPES: ArtefactType[] = [
  "advisory",
  "executive_summary",
  "linkedin_post",
  "x_thread",
  "presentation",
  "video_package",
  "infographic",
];

export const ARTEFACT_LABELS: Record<string, string> = {
  advisory: "Advisory",
  executive_summary: "Executive Summary",
  linkedin_post: "LinkedIn Post",
  x_thread: "Twitter/X Thread",
  presentation: "Presentation",
  video_package: "Video Package",
  infographic: "Infographic",
};

export const FIELD_LABELS: Record<string, string> = {
  severity: "Severity",
  executive_summary: "Executive Summary",
  affected_systems: "Affected Systems",
  details: "Details",
  iocs: "Indicators of Compromise",
  mitigations: "Mitigations",
  references: "References",
  title: "Title",
  summary: "Summary",
  key_points: "Key Points",
  recommendations: "Recommendations",
  headline: "Headline",
  body: "Body",
  cta: "Call to Action",
  hashtags: "Hashtags",
  tweets: "Thread",
  script: "Script",
  storyboard: "Storyboard",
  scene_descriptions: "Scene Descriptions",
  narration: "Narration",
  subtitles: "Subtitles",
  visual_recommendations: "Visual Recommendations",
  content: "Content",
  layout_recommendations: "Layout Recommendations",
  key_messaging: "Key Messaging",
  slides: "Slides",
  bullets: "Bullets",
  speaker_notes: "Speaker Notes",
};

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function artefactLabel(type: string): string {
  return ARTEFACT_LABELS[type] ?? fieldLabel(type);
}
