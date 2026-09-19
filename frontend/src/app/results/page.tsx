"use client";

import { AlertTriangle, CheckCircle2, Copy, Download, FileText, Loader2, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
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
  const [busy, setBusy] = useState(false);
  const [instruction, setInstruction] = useState("");
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
    setBusy(true);
    setError("");
    try {
      await resumeRun(threadId, decision);
      setInstruction("");
      setReloadToken((token) => token + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "unknown error");
    } finally {
      setBusy(false);
    }
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

      {run?.warnings?.length ? (
        <div className="relay-panel" style={{ marginBottom: 16 }}>
          <div className="relay-panel-header"><div><span className="relay-index">note</span><h2>Ingestion warnings</h2></div></div>
          <ul>{run.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </div>
      ) : null}

      {run?.status === "running" ? (
        <div className="relay-panel" style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Loader2 size={16} className="relay-spinner" />
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
          <div className="relay-panel">
            <div className="relay-panel-header"><div><span className="relay-index">checks</span><h2>Fact verification</h2></div>{flagged.length ? <ShieldAlert size={15} /> : <ShieldCheck size={15} />}</div>
            {check?.meta ? <div className="relay-summary-row"><span>support ratio</span><strong>{Math.round((check.meta.support_ratio ?? 0) * 100)}%</strong></div> : null}
            {check?.meta ? <div className="relay-summary-row"><span>claims checked</span><strong>{check.meta.sentences_checked ?? verdicts.length}</strong></div> : null}
            {check?.meta?.unverified_iocs?.length ? <div className="relay-summary-row"><span>unverified IoCs</span><strong>{check.meta.unverified_iocs.join(", ")}</strong></div> : null}
            <div style={{ maxHeight: 260, overflowY: "auto", marginTop: 8 }}>
              {verdicts.map((verdict, index) => (
                <div key={index} style={{ display: "flex", gap: 8, padding: "6px 0", borderTop: "1px solid var(--relay-border, #262626)" }}>
                  {verdict.verdict === "supported" ? <CheckCircle2 size={14} style={{ color: "#41b883", flexShrink: 0, marginTop: 2 }} /> : <AlertTriangle size={14} style={{ color: "#e0a33a", flexShrink: 0, marginTop: 2 }} />}
                  <div>
                    <small style={{ display: "block", opacity: 0.9 }}>{verdict.claim}</small>
                    <small style={{ opacity: 0.55 }}>{verdict.verdict}{verdict.citation ? ` · ${verdict.citation}` : ""}</small>
                  </div>
                </div>
              ))}
              {!verdicts.length ? <p className="relay-panel-description">No verdicts for this artefact.</p> : null}
            </div>
          </div>

          <div className="relay-panel">
            <div className="relay-panel-header"><div><span className="relay-index">review</span><h2>Human review</h2></div></div>
            <p className="relay-panel-description">{awaiting ? "This run is paused for your decision." : "Approve, or request a rewrite of specific artefacts."}</p>
            {awaiting ? (
              <>
                <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="optional: what should change? e.g. shorten the advisory and add patch urgency" />
                <button className="relay-generate" type="button" disabled={busy} onClick={() => resend({ action: "refine", instruction, types: activeType ? [activeType] : [] })}><RefreshCw size={14} /> Refine {activeType ? artefactLabel(activeType) : ""}</button>
                <button className="relay-generate" type="button" disabled={busy} onClick={() => resend({ action: "accept" })}><CheckCircle2 size={14} /> Accept &amp; export</button>
              </>
            ) : (
              <div className="relay-summary-row"><span>decision</span><strong>{run?.review?.action ?? "—"}</strong></div>
            )}
          </div>

          <div className="relay-panel">
            <div className="relay-panel-header"><div><span className="relay-index">source</span><h2>Sources</h2></div></div>
            {(run?.sources ?? []).map((source) => (
              <div key={source.source_id} className="relay-summary-row"><span>{source.kind}</span><strong>{source.source_id}</strong></div>
            ))}
            {run?.content_model?.entities?.length ? <div className="relay-summary-row"><span>entities</span><strong>{run.content_model.entities.slice(0, 5).join(", ")}</strong></div> : null}
            {run?.content_model?.iocs?.length ? <div className="relay-summary-row"><span>iocs</span><strong>{run.content_model.iocs.slice(0, 5).join(", ")}</strong></div> : null}
          </div>

          {run?.export?.files?.length ? (
            <div className="relay-panel">
              <div className="relay-panel-header"><div><span className="relay-index">export</span><h2>Export pack</h2></div></div>
              {run.export.files.map((file) => (
                <div key={`${file.type}-${file.ext}`} className="relay-summary-row">
                  <span>{file.type}.{file.ext}</span>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                    <FilePreview
                      threadId={threadId}
                      type={file.type}
                      ext={file.ext}
                      draft={run?.artefacts?.[file.type]}
                    />
                    <a href={downloadUrl(threadId, file.type, file.ext)} style={{ color: "inherit" }}>{(file.bytes / 1024).toFixed(1)} KB</a>
                  </span>
                </div>
              ))}
              {run.export.render_error ? <p className="relay-panel-description">render error: {run.export.render_error}</p> : null}
            </div>
          ) : null}
        </aside>
      </div>
    </Shell>
  );
}
