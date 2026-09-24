"use client";

import { CheckCircle2, Copy, Download, FileText, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArtefactPreview } from "@/components/artefact-previews";
import { AppSidebar } from "@/components/app-sidebar";
import { FilePreview } from "@/components/file-preview";
import { downloadUrl, getRun, resumeRun } from "@/lib/api";
import { artefactLabel, type RunDetail } from "@/lib/types";

export default function ResultsPage() {
  return (
    <Suspense fallback={<Shell><p className="relay-panel-description">Loading run…</p></Shell>}>
      <ResultsView />
    </Suspense>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="relay-shell">
      <AppSidebar />
      <section className="relay-main">
        <header className="relay-topbar"><div className="relay-breadcrumb"><span>relay</span><span>/</span><strong>results</strong></div><div className="relay-top-actions"><span className="relay-avatar">AI</span></div></header>
        <div className="relay-results-content">{children}</div>
      </section>
    </main>
  );
}

// Per-artefact rendering now lives in components/artefact-previews.tsx, where a
// generic field walk was replaced by a tailored preview per output type.

function ResultsView() {
  const threadId = useSearchParams().get("id") ?? "";
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");
  const [busyAction, setBusyAction] = useState<"" | "refine" | "accept">("");
  const [instruction, setInstruction] = useState("");
  const [hint, setHint] = useState("");
  const instructionRef = useRef<HTMLTextAreaElement>(null);
  const busy = busyAction !== "";
  const [reloadToken, setReloadToken] = useState(0);
  const [active, setActive] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!threadId) return;
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const detail = await getRun(threadId);
        if (cancelled) return;
        setRun(detail);
        setError("");
        setActive((current) => current || Object.keys(detail.artefacts ?? {})[0] || "");
        if (detail.status === "running") timer = window.setTimeout(tick, 2000);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "unknown error");
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [threadId, reloadToken]);

  const artefactTypes = useMemo(() => Object.keys(run?.artefacts ?? {}), [run]);
  const activeType = active || artefactTypes[0] || "";
  const draft = run?.artefacts?.[activeType];
  const check = run?.fact_checks?.[activeType];
  const verdicts = check?.verdicts ?? [];
  const flagged = verdicts.filter((verdict) => verdict.verdict !== "supported");

  const resend = async (decision: { action: "accept" | "refine"; instruction?: string; types?: string[] }) => {
    if (!threadId) return;
    setBusyAction(decision.action);
    setError("");
    setHint("");
    try {
      await resumeRun(threadId, decision);
      setInstruction("");
      setReloadToken((token) => token + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "unknown error");
    } finally {
      setBusyAction("");
    }
  };

  // The engine refuses a refine without an instruction, so catch it here and
  // point at the field instead of letting the request fail.
  const requestRefine = () => {
    if (!instruction.trim()) {
      setHint("Describe what should change, or accept the draft as it is.");
      instructionRef.current?.focus();
      return;
    }
    void resend({ action: "refine", instruction, types: activeType ? [activeType] : [] });
  };

  const copyDraft = async () => {
    if (!draft) return;
    await navigator.clipboard?.writeText(JSON.stringify(draft, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  if (!threadId) {
    return (
      <Shell>
        <div className="relay-page-heading"><div><p className="relay-kicker">no run selected</p><h1>Nothing to show yet</h1><p>Start a run from the dashboard to see artefacts here.</p></div></div>
        <Link href="/dashboard" className="relay-generate" style={{ display: "inline-flex", width: "auto", padding: "10px 16px" }}>Go to dashboard</Link>
      </Shell>
    );
  }

  const awaiting = run?.status === "awaiting_review";

  return (
    <Shell>
      <div className="relay-page-heading">
        <div>
          <p className="relay-kicker">{threadId} / results</p>
          <h1>{run?.content_model?.title || run?.label || "Run results"}</h1>
          <p>
            {run ? `${artefactTypes.length} artefact${artefactTypes.length === 1 ? "" : "s"}` : "loading…"}
            {run?.content_model?.severity ? ` · severity ${run.content_model.severity}` : ""}
            {run?.content_model?.source_type ? ` · ${run.content_model.source_type}` : ""}
          </p>
        </div>
        <span className="relay-run-id">{run?.status === "running" ? "processing…" : run?.status ?? "loading"}</span>
      </div>

      {error && <div className="relay-panel relay-error-panel" style={{ marginBottom: 16 }}><strong>Error</strong><p>{error}</p></div>}

      {run?.status === "running" ? (
        <div className="relay-panel" style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="relay-spinner" aria-hidden="true" />
          <span>Ingesting sources and generating deliverables — this can take a few minutes.</span>
        </div>
      ) : null}

      <div className="relay-results-layout" style={{ marginTop: 16 }}>
        <section className="relay-document-panel">
          <div className="relay-document-toolbar">
            <div className="relay-document-title"><FileText size={15} /><span>{activeType}.{run?.export?.files?.find((file) => file.type === activeType)?.ext ?? "md"}</span></div>
            <div className="relay-document-actions">
              <button type="button" onClick={copyDraft} disabled={!draft}><Copy size={13} /> {copied ? "copied" : "copy"}</button>
              {(run?.export?.files ?? []).filter((file) => file.type === activeType).map((file) => (
                <span key={file.ext} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <FilePreview threadId={threadId} type={file.type} ext={file.ext} draft={draft} />
                  <a href={downloadUrl(threadId, file.type, file.ext)} style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "inherit", textDecoration: "none" }}>
                    <Download size={13} /> {file.ext}
                  </a>
                </span>
              ))}
            </div>
          </div>

          {artefactTypes.length ? (
            <div className="relay-tabs">
              {artefactTypes.map((type) => (
                <button className={activeType === type ? "active" : ""} key={type} type="button" onClick={() => setActive(type)}>{artefactLabel(type)}</button>
              ))}
            </div>
          ) : null}

          <article className="relay-document">
            {draft ? (
              <>
                <span className="relay-document-eyebrow">{activeType} · {artefactLabel(activeType)}</span>
                <h2>{run?.content_model?.title || artefactLabel(activeType)}</h2>
                <div className="relay-doc-rule" />
                <ArtefactPreview
                  type={activeType}
                  draft={draft}
                  threadId={threadId}
                  severity={run?.content_model?.severity}
                />
              </>
            ) : (
              <p className="relay-panel-description">No artefact yet.</p>
            )}
            <div className="relay-document-footer">
              <span>source: {run?.sources?.map((item) => item.source_id).join(", ") || "—"}</span>
              <span>review status: {run?.review?.action ?? (awaiting ? "awaiting operator" : "—")}</span>
            </div>
          </article>
        </section>

        <aside className="relay-results-sidebar">
          <div className="relay-inspector">
            <section className="relay-insp-section">
              <header className="relay-insp-head">
                <h2>Fact verification</h2>
                <span className={`relay-insp-badge ${flagged.length ? "warn" : "ok"}`}>
                  {flagged.length ? `${flagged.length} flagged` : "all supported"}
                </span>
              </header>

              {check?.meta ? (
                <>
                  <div className="relay-metric">
                    <div className="relay-metric-top">
                      <span className="relay-metric-value">{Math.round((check.meta.support_ratio ?? 0) * 100)}%</span>
                      <span className="relay-metric-label">claims grounded in the source</span>
                    </div>
                    <div className="relay-meter">
                      <i style={{ width: `${Math.round((check.meta.support_ratio ?? 0) * 100)}%` }} />
                    </div>
                  </div>
                  <p className="relay-insp-note">
                    {check.meta.sentences_checked ?? verdicts.length} claims checked
                    {check.meta.unverified_iocs?.length ? ` · ${check.meta.unverified_iocs.length} unverified IoCs` : ""}
                  </p>
                </>
              ) : null}

              <ul className="relay-verdicts">
                {verdicts.map((verdict, index) => (
                  <li className={`relay-verdict ${verdict.verdict === "supported" ? "ok" : "flag"}`} key={index}>
                    <span className="relay-verdict-dot" aria-hidden="true" />
                    <div>
                      <p className="relay-verdict-claim">{verdict.claim}</p>
                      <p className="relay-verdict-meta">
                        {verdict.verdict}
                        {verdict.citation ? ` · ${verdict.citation}` : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
              {!verdicts.length ? <p className="relay-insp-note">No verdicts for this artefact.</p> : null}
            </section>

            <section className="relay-insp-section">
              <header className="relay-insp-head">
                <h2>Human review</h2>
                {awaiting ? <span className="relay-insp-badge warn">paused</span> : null}
              </header>
              <p className="relay-insp-note">
                {awaiting ? "This run is paused for your decision." : "Approve, or request a rewrite of specific artefacts."}
              </p>
              {awaiting ? (
                <>
                  <label className="relay-review-note">
                    <span>Refine instruction</span>
                    <textarea
                      ref={instructionRef}
                      value={instruction}
                      onChange={(event) => { setInstruction(event.target.value); if (hint) setHint(""); }}
                      placeholder="What should change? e.g. shorten the advisory and lead with the patch"
                    />
                  </label>
                  {hint ? <p className="relay-review-hint">{hint}</p> : null}
                  <p className="relay-review-consequence">
                    Accepting renders every artefact and writes the export manifest.
                    {activeType ? ` Refining rewrites only the ${artefactLabel(activeType).toLowerCase()}.` : ""}
                  </p>
                  <div className="relay-review-actions">
                    <button className="relay-btn relay-btn-secondary" type="button" disabled={busy} onClick={requestRefine}>
                      {busyAction === "refine" ? <span className="relay-spinner" aria-hidden="true" /> : <RefreshCw size={14} />}
                      {busyAction === "refine" ? "Refining…" : `Refine ${activeType ? artefactLabel(activeType) : ""}`.trim()}
                    </button>
                    <button className="relay-btn relay-btn-primary" type="button" disabled={busy} onClick={() => resend({ action: "accept" })}>
                      {busyAction === "accept" ? <span className="relay-spinner" aria-hidden="true" /> : <CheckCircle2 size={14} />}
                      {busyAction === "accept" ? "Exporting…" : "Accept & export"}
                    </button>
                  </div>
                </>
              ) : (
                <div className="relay-insp-fact">
                  <span>decision</span>
                  <strong>{run?.review?.action ?? "—"}</strong>
                </div>
              )}
            </section>

            <section className="relay-insp-section">
              <header className="relay-insp-head"><h2>Sources</h2></header>
              <ul className="relay-src-list">
                {(run?.sources ?? []).map((source) => (
                  <li key={source.source_id}>
                    <span className="relay-chip">{source.kind}</span>
                    <span className="relay-src-name" title={source.source_id}>{source.source_id}</span>
                  </li>
                ))}
              </ul>
              {run?.content_model?.entities?.length ? (
                <div className="relay-chip-row">
                  <span className="relay-insp-label">entities</span>
                  {run.content_model.entities.slice(0, 6).map((entity) => <span className="relay-chip" key={entity}>{entity}</span>)}
                </div>
              ) : null}
              {run?.content_model?.iocs?.length ? (
                <div className="relay-chip-row">
                  <span className="relay-insp-label">indicators</span>
                  {run.content_model.iocs.slice(0, 6).map((ioc) => <span className="relay-chip mono" key={ioc}>{ioc}</span>)}
                </div>
              ) : null}
            </section>

            {run?.export?.files?.length ? (
              <section className="relay-insp-section">
                <header className="relay-insp-head">
                  <h2>Export pack</h2>
                  <span className="relay-insp-badge">{run.export.files.length} files</span>
                </header>
                <ul className="relay-export-list">
                  {run.export.files.map((file) => (
                    <li key={`${file.type}-${file.ext}`}>
                      <span className="relay-export-name">{file.type}.<em>{file.ext}</em></span>
                      <span className="relay-export-actions">
                        <FilePreview
                          threadId={threadId}
                          type={file.type}
                          ext={file.ext}
                          draft={run?.artefacts?.[file.type]}
                        />
                        <a className="relay-export-size" href={downloadUrl(threadId, file.type, file.ext)}>
                          {(file.bytes / 1024).toFixed(1)} KB
                        </a>
                      </span>
                    </li>
                  ))}
                </ul>
                {run.export.render_error ? <p className="relay-insp-note">render error: {run.export.render_error}</p> : null}
              </section>
            ) : null}
          </div>
        </aside>
      </div>
    </Shell>
  );
}
