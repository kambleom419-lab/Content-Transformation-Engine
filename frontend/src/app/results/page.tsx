"use client";

import { Copy, Download, FileText, RefreshCw } from "lucide-react";
import { useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";

const tabs = ["Executive Summary", "LinkedIn Post", "Twitter/X Thread", "Presentation", "Advisory", "Video Script"];

export default function ResultsPage() {
  const [active, setActive] = useState(tabs[0]);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard?.writeText("The programme has made steady progress across priority departments...");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  return (
    <main className="relay-shell">
      <AppSidebar />
      <section className="relay-main">
        <header className="relay-topbar"><div className="relay-breadcrumb"><span>relay</span><span>/</span><strong>results</strong></div><div className="relay-top-actions"><span className="relay-status"><i /> run complete</span><span className="relay-avatar">AI</span></div></header>
        <div className="relay-results-content">
          <div className="relay-page-heading"><div><p className="relay-kicker">run_2025_0148 / results</p><h1>Digital services programme</h1><p>Generated 2 minutes ago from <strong>digital-services-programme.docx</strong></p></div><span className="relay-run-id">v3 · 6 outputs</span></div>
          <div className="relay-results-layout">
            <section className="relay-document-panel">
              <div className="relay-document-toolbar"><div className="relay-document-title"><FileText size={15} /><span>{active.toLowerCase().replaceAll(" ", "_")}.md</span></div><div className="relay-document-actions"><button type="button" onClick={copy}><Copy size={13} /> {copied ? "copied" : "copy"}</button><button type="button"><Download size={13} /> export</button><button type="button"><RefreshCw size={13} /> regenerate</button></div></div>
              <div className="relay-tabs">{tabs.map((tab) => <button className={active === tab ? "active" : ""} key={tab} type="button" onClick={() => setActive(tab)}>{tab}</button>)}</div>
              <article className="relay-document">
                <span className="relay-document-eyebrow">executive_summary.md</span>
                <h2>{active}</h2>
                <div className="relay-doc-rule" />
                <p>The Ministry&apos;s Digital Public Services Programme has made steady progress across citizen-facing departments, with 68% of priority services now available online.</p>
                <p>The next phase should focus on improving adoption in rural districts, strengthening accessibility standards, and establishing a consistent measurement framework across departments.</p>
                <h3>Key observations</h3>
                <ul><li>Online availability has expanded across priority services.</li><li>Adoption remains uneven across regions.</li><li>Accessibility and measurement are the next operational priorities.</li></ul>
                <div className="relay-document-footer"><span>source: digital-services-programme.docx</span><span>review status: pending</span></div>
              </article>
            </section>
            <aside className="relay-results-sidebar">
              <div className="relay-panel"><div className="relay-panel-header"><div><span className="relay-index">source</span><h2>Source metadata</h2></div></div><div className="relay-meta-file"><FileText size={14} /><span>digital-services-programme.docx</span></div><div className="relay-summary-row"><span>audience</span><strong>Government communications</strong></div><div className="relay-summary-row"><span>tone</span><strong>Formal</strong></div><div className="relay-summary-row"><span>language</span><strong>English</strong></div></div>
              <div className="relay-panel"><div className="relay-panel-header"><div><span className="relay-index">history</span><h2>Version history</h2></div></div><div className="relay-version active"><span>v3</span><div><strong>Current output</strong><small>just now · Alex Iyer</small></div></div><div className="relay-version"><span>v2</span><div><strong>Updated audience</strong><small>2 min ago</small></div></div><div className="relay-version"><span>v1</span><div><strong>Initial generation</strong><small>4 min ago</small></div></div></div>
            </aside>
          </div>
        </div>
      </section>
    </main>
  );
}
