"use client";

import { Check, ChevronDown, File as FileIcon, FileImage, FileText, FileVideo, Image, MoreHorizontal, Play, Presentation, Settings2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import { StarsBackground } from "@/components/animate-ui/components/backgrounds/stars";

const outputs = [
  { label: "Executive Summary", detail: "Concise decision brief", icon: FileText },
  { label: "Presentation", detail: "Structured slide outline", icon: Presentation },
  { label: "LinkedIn Post", detail: "Professional social post", icon: FileText },
  { label: "Twitter/X Thread", detail: "Short-form thread", icon: FileText },
  { label: "Advisory", detail: "Clear public guidance", icon: FileText },
  { label: "Infographic", detail: "Visual information brief", icon: Image },
  { label: "Video Package", detail: "Script and scene outline", icon: FileVideo },
];

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return <label className="relay-field"><span>{label}</span><div className="relay-select"><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select><ChevronDown size={14} /></div></label>;
}

export default function DashboardPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [source, setSource] = useState("");
  const [audience, setAudience] = useState("Government communications");
  const [tone, setTone] = useState("Formal");
  const [language, setLanguage] = useState("English");
  const [objective, setObjective] = useState("Inform");
  const [selected, setSelected] = useState(["Executive Summary"]);
  const [dragging, setDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadState, setUploadState] = useState<"idle" | "uploading" | "success">("idle");
  const chooseFile = (file?: File) => {
    if (!file) return;
    setFileName(file.name);
    setUploadProgress(0);
    setUploadState("uploading");
  };
  useEffect(() => {
    if (uploadState !== "uploading") return;
    const timer = window.setInterval(() => {
      setUploadProgress((current) => {
        const next = Math.min(current + 17, 100);
        if (next === 100) {
          window.clearInterval(timer);
          setUploadState("success");
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [uploadState]);
  const fileExtension = fileName.split(".").pop()?.toLowerCase();
  const FileTypeIcon = fileExtension === "png" || fileExtension === "jpg" || fileExtension === "jpeg" ? FileImage : fileExtension === "mp4" ? FileVideo : fileExtension === "pdf" || fileExtension === "docx" || fileExtension === "txt" ? FileText : FileIcon;
  const fileTypeLabel = fileExtension ? fileExtension.toUpperCase() : "";
  const toggleOutput = (output: string) => setSelected((current) => current.includes(output) ? current.filter((item) => item !== output) : [...current, output]);

  return <main className="relay-shell relative overflow-hidden"><AppSidebar />
  
  <section className="relay-main">
            
    <header className="relay-topbar"><div className="relay-breadcrumb"><span>relay</span><span>/</span><strong>dashboard</strong></div><div className="relay-top-actions"><span className="relay-status"><i /> workspace online</span><span className="relay-command">⌘ K</span><div className="relay-avatar">AI</div></div></header>
    <div className="relay-content">
      <div className="relay-page-heading"><div><p className="relay-kicker">workspace / dashboard</p><h1>One source. Multiple deliverables.</h1><p>Transform source material into clear, reviewable content for every channel.</p></div><span className="relay-run-id">run_2025_0148</span></div>
      <div className="relay-grid">
        <section className="relay-editor-column">

          <div className={`relay-panel relay-upload-panel ${dragging ? "is-dragging" : ""} ${fileName ? "has-file" : ""} upload-state-${uploadState}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0]); }}>
            <input ref={inputRef} hidden type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.mp4" onChange={(event) => chooseFile(event.target.files?.[0])} />
            <div className="relay-panel-header"><div><span className="relay-index">01</span><h2>Upload source material</h2></div><span className="relay-panel-meta">{uploadState === "success" ? "ready" : "input"}</span></div>
            <button className="relay-dropzone" type="button" onClick={() => inputRef.current?.click()}>
              <span className="relay-upload-icon">{fileName ? (uploadState === "success" ? <Check size={19} /> : <FileTypeIcon size={19} />) : <Upload size={19} />}</span>
              <span className="relay-upload-copy"><strong>{fileName || "Drop your source material here"}</strong><small>{fileName ? `${fileTypeLabel} · ${uploadState === "success" ? "Upload complete" : `Uploading ${uploadProgress}%`}` : "Drag and drop files or browse from your device"}</small></span>
              <em>{fileName ? "change file" : "browse files"}</em>
              {fileName && uploadState !== "success" && <span className="relay-upload-progress"><i style={{ width: `${uploadProgress}%` }} /></span>}
            </button>
            <div className="relay-upload-formats"><span>Accepted formats</span><strong>PDF</strong><strong>DOCX</strong><strong>TXT</strong><strong>PNG</strong><strong>JPG</strong><strong>MP4</strong></div>
            <div className="relay-file-note"><span>max 50 MB per file</span><span>{uploadState === "success" ? "source stored securely" : "private workspace storage"}</span></div>
          </div>
          <div className="relay-panel relay-source-panel"><div className="relay-panel-header"><div><span className="relay-index">02</span><h2>Source content</h2></div><span className="relay-character-count">{source.length} / 10,000</span></div><textarea value={source} onChange={(event) => setSource(event.target.value.slice(0, 10000))} placeholder="// paste source material or add working notes..." /><div className="relay-editor-footer"><span>Plain text input is processed alongside uploaded material.</span><span>markdown supported</span></div></div>
          <div className="relay-panel relay-config-panel"><div className="relay-panel-header"><div><span className="relay-index">03</span><h2>Configuration</h2></div><Settings2 size={15} className="relay-muted-icon" /></div><p className="relay-panel-description">Set the intended audience, voice, language, and purpose for this run.</p><div className="relay-fields"><SelectField label="Audience" value={audience} onChange={setAudience} options={["Executive", "Citizen", "Analyst", "Student"]} /><SelectField label="Tone" value={tone} onChange={setTone} options={["Professional", "Formal", "Technical", "Simplified"]} /><SelectField label="Language" value={language} onChange={setLanguage} options={["English", "Hindi", "Regional Language"]} /><SelectField label="Content objective" value={objective} onChange={setObjective} options={["Inform", "Advise", "Summarize", "Promote"]} /></div></div>
        </section>
        <aside className="relay-output-column"><div className="relay-panel relay-output-panel"><div className="relay-panel-header"><div><span className="relay-index">04</span><h2>Output formats</h2></div><span className="relay-count">{selected.length}</span></div><p className="relay-panel-description">Select one or more deliverables to prepare from this source.</p><div className="relay-output-list">{outputs.map(({ label, detail, icon: Icon }) => { const isSelected = selected.includes(label); return <button className={`relay-output-option ${isSelected ? "selected" : ""}`} type="button" key={label} aria-pressed={isSelected} onClick={() => toggleOutput(label)}><span className="relay-output-icon"><Icon size={15} /></span><span className="relay-output-copy"><strong>{label}</strong><small>{detail}</small></span><span className="relay-checkbox">{isSelected ? <Check size={12} /> : ""}</span></button>; })}</div></div><div className="relay-panel relay-summary-panel"><div className="relay-panel-header"><h2>Run context</h2><MoreHorizontal size={15} className="relay-muted-icon" /></div><div className="relay-summary-row"><span>source</span><strong>{fileName || (source ? "inline text" : "awaiting input")}</strong></div><div className="relay-summary-row"><span>audience</span><strong>{audience}</strong></div><div className="relay-summary-row"><span>objective</span><strong>{objective}</strong></div><div className="relay-summary-row"><span>language</span><strong>{language}</strong></div></div><button className="relay-generate" type="button" disabled={(!fileName && !source.trim()) || selected.length === 0}><Play size={14} fill="currentColor" /> Generate deliverables <span>↵</span></button><div className="relay-shortcut"><span>secure execution</span><span>⌘ ↵</span></div></aside>
      </div>
    </div>
  </section></main>;
}
