"use client";

import { Check, ChevronDown, File as FileIcon, FileImage, FileText, FileVideo, Image, MoreHorizontal, Play, Presentation, Settings2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import { TemplatePicker } from "@/components/template-picker";
import { getRun, startRunWithFiles } from "@/lib/api";
import type { RunStatus } from "@/lib/types";

const OUTPUT_OPTIONS = [
  { type: "executive_summary", label: "Executive Summary", detail: "Concise decision brief", icon: FileText },
  { type: "presentation", label: "Presentation", detail: "Structured slide outline", icon: Presentation },
  { type: "linkedin_post", label: "LinkedIn Post", detail: "Professional social post", icon: FileText },
  { type: "x_thread", label: "Twitter/X Thread", detail: "Short-form thread", icon: FileText },
  { type: "advisory", label: "Advisory", detail: "Clear public guidance", icon: FileText },
  { type: "infographic", label: "Infographic", detail: "Visual information brief", icon: Image },
  { type: "video_package", label: "Video Package", detail: "Script and scene outline", icon: FileVideo },
];

const STATUS_TEXT: Record<RunStatus, string> = {
  running: "processing…",
  awaiting_review: "awaiting review",
  complete: "complete",
  failed: "failed",
};

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return <label className="relay-field"><span>{label}</span><div className="relay-select"><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select><ChevronDown size={14} /></div></label>;
}

export default function DashboardPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [source, setSource] = useState("");
  const [audience, setAudience] = useState("Executive");
  const [tone, setTone] = useState("Formal");
  const [language, setLanguage] = useState("English");
  const [objective, setObjective] = useState("Inform");
  const [selected, setSelected] = useState<string[]>(["executive_summary"]);
  const [template, setTemplate] = useState("classic");
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState("");
  const busy = status === "running";

  const addFiles = (incoming: FileList | null) => {
    if (!incoming?.length) return;
    setFiles((current) => [...current, ...Array.from(incoming)]);
    setError("");
  };

  const toggleOutput = (type: string) =>
    setSelected((current) => (current.includes(type) ? current.filter((item) => item !== type) : [...current, type]));

  const generate = async () => {
    setError("");
    setStatus("running");
    try {
      const payload = {
        selected_outputs: selected,
        params: { target_audience: audience, tone, language, communication_objective: objective, template },
        sources: source.trim() ? [{ kind: "text", text: source.trim(), id: "pasted-source" }] : [],
        label: files[0]?.name ?? (source.trim() ? "pasted source" : ""),
      };
      const started = await startRunWithFiles(files, payload);

      for (let attempt = 0; attempt < 900; attempt += 1) {
        const run = await getRun(started.thread_id);
        setStatus(run.status);
        if (run.status === "failed") {
          setError(run.error ?? "the engine reported a failure");
          return;
        }
        if (run.status !== "running") {
          router.push(`/results?id=${started.thread_id}`);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      setError("timed out waiting for the run");
    } catch (caught) {
      setStatus("failed");
      setError(caught instanceof Error ? caught.message : "unknown error");
    }
  };

  const primaryLabel = files[0]?.name ?? (source.trim() ? "pasted source" : "");
  const primaryExt = files[0]?.name.split(".").pop()?.toLowerCase() ?? "";
  const usesTemplate = selected.includes("presentation") || selected.includes("infographic");
  const FileTypeIcon = ["png", "jpg", "jpeg", "webp"].includes(primaryExt) ? FileImage : ["mp4", "mov", "webm"].includes(primaryExt) ? FileVideo : primaryExt ? FileText : FileIcon;

  return <main className="relay-shell relative overflow-hidden"><AppSidebar />

  <section className="relay-main">

    <header className="relay-topbar"><div className="relay-breadcrumb"><span>relay</span><span>/</span><strong>dashboard</strong></div><div className="relay-top-actions"><span className="relay-status"><i /> {status ? STATUS_TEXT[status] : "workspace online"}</span><span className="relay-command">⌘ K</span><div className="relay-avatar">AI</div></div></header>
    <div className="relay-content">
      <div className="relay-page-heading"><div><p className="relay-kicker">workspace / dashboard</p><h1>One source. Multiple deliverables.</h1><p>Transform source material into clear, reviewable content for every channel.</p></div><span className="relay-run-id">{status ? STATUS_TEXT[status] : "idle"}</span></div>
      <div className="relay-grid">
        <section className="relay-editor-column">

          <div className={`relay-panel relay-upload-panel ${dragging ? "is-dragging" : ""} ${files.length ? "has-file" : ""} upload-state-${files.length ? "success" : "idle"}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}>
            <input ref={inputRef} hidden multiple type="file" accept=".pdf,.docx,.pptx,.xlsx,.txt,.md,.html,.png,.jpg,.jpeg,.webp,.mp3,.wav,.ogg,.mp4,.mov" onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
            <div className="relay-panel-header"><div><span className="relay-index">01</span><h2>Upload source material</h2></div><span className="relay-panel-meta">{files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : "input"}</span></div>
            <button className="relay-dropzone" type="button" onClick={() => inputRef.current?.click()}>
              <span className="relay-upload-icon">{files.length ? <Check size={19} /> : <Upload size={19} />}</span>
              <span className="relay-upload-copy"><strong>{primaryLabel || "Drop your source material here"}</strong><small>{files.length ? `${files.length} file${files.length > 1 ? "s" : ""} staged · ${primaryExt ? primaryExt.toUpperCase() : ""}` : "Drag and drop files or browse from your device"}</small></span>
              <em>{files.length ? "add more" : "browse files"}</em>
            </button>
            {files.length > 0 && <div className="relay-file-note">{files.map((file, index) => <span key={`${file.name}-${index}`}><FileTypeIcon size={12} /> {file.name}</span>)}</div>}
            <div className="relay-upload-formats"><span>Accepted formats</span><strong>PDF</strong><strong>DOCX</strong><strong>PPTX</strong><strong>XLSX</strong><strong>PNG</strong><strong>MP3</strong><strong>MP4</strong></div>
            <div className="relay-file-note"><span>multiple sources supported</span><span>{files.length ? "staged locally" : "private workspace storage"}</span></div>
          </div>
          <div className="relay-panel relay-source-panel"><div className="relay-panel-header"><div><span className="relay-index">02</span><h2>Source content</h2></div><span className="relay-character-count">{source.length} / 10,000</span></div><textarea value={source} onChange={(event) => setSource(event.target.value.slice(0, 10000))} placeholder="// paste source material or add working notes..." /><div className="relay-editor-footer"><span>Plain text input is processed alongside uploaded material.</span><span>markdown supported</span></div></div>
          <div className="relay-panel relay-config-panel"><div className="relay-panel-header"><div><span className="relay-index">03</span><h2>Configuration</h2></div><Settings2 size={15} className="relay-muted-icon" /></div><p className="relay-panel-description">Set the intended audience, voice, language, and purpose for this run.</p><div className="relay-fields"><SelectField label="Audience" value={audience} onChange={setAudience} options={["Executive", "Citizen", "Analyst", "Student", "Government communications"]} /><SelectField label="Tone" value={tone} onChange={setTone} options={["Professional", "Formal", "Technical", "Simplified"]} /><SelectField label="Language" value={language} onChange={setLanguage} options={["English", "Hindi"]} /><SelectField label="Content objective" value={objective} onChange={setObjective} options={["Inform", "Advise", "Summarize", "Promote"]} /></div></div>
        </section>
        <aside className="relay-output-column"><div className="relay-panel relay-output-panel"><div className="relay-panel-header"><div><span className="relay-index">04</span><h2>Output formats</h2></div><span className="relay-count">{selected.length}</span></div><p className="relay-panel-description">Select one or more deliverables to prepare from this source.</p><div className="relay-output-list">{OUTPUT_OPTIONS.map(({ type, label, detail, icon: Icon }) => { const isSelected = selected.includes(type); return <button className={`relay-output-option ${isSelected ? "selected" : ""}`} type="button" key={type} aria-pressed={isSelected} onClick={() => toggleOutput(type)}><span className="relay-output-icon"><Icon size={15} /></span><span className="relay-output-copy"><strong>{label}</strong><small>{detail}</small></span><span className="relay-checkbox">{isSelected ? <Check size={12} /> : ""}</span></button>; })}</div></div><div className="relay-panel relay-template-panel"><div className="relay-panel-header"><div><span className="relay-index">05</span><h2>Template</h2></div><span className="relay-panel-meta">{usesTemplate ? "in use" : "optional"}</span></div><p className="relay-panel-description">{usesTemplate ? "Applies to the deck and the poster. Pick a look by seeing it — the eye opens a sample full size." : "Applies to the Presentation deck and the Infographic poster. Pick one now, then tick Presentation or Infographic above to use it."}</p><TemplatePicker value={template} onChange={setTemplate} /></div><div className="relay-panel relay-summary-panel"><div className="relay-panel-header"><h2>Run context</h2><MoreHorizontal size={15} className="relay-muted-icon" /></div><div className="relay-summary-row"><span>source</span><strong>{primaryLabel || "awaiting input"}</strong></div><div className="relay-summary-row"><span>audience</span><strong>{audience}</strong></div><div className="relay-summary-row"><span>objective</span><strong>{objective}</strong></div><div className="relay-summary-row"><span>language</span><strong>{language}</strong></div>{usesTemplate ? <div className="relay-summary-row"><span>template</span><strong>{template}</strong></div> : null}</div>{error && <div className="relay-panel relay-error-panel"><strong>Run failed</strong><p>{error}</p></div>}<button className="relay-generate" type="button" onClick={generate} disabled={busy || (!files.length && !source.trim()) || selected.length === 0}>{busy ? <><RefreshSpinner /> Generating…</> : <><Play size={14} fill="currentColor" /> Generate deliverables <span>↵</span></>}</button><div className="relay-shortcut"><span>secure execution</span><span>{selected.length} output{selected.length === 1 ? "" : "s"}</span></div></aside>
      </div>
    </div>
  </section></main>;
}

function RefreshSpinner() {
  return <span className="relay-spinner" aria-hidden="true" />;
}
