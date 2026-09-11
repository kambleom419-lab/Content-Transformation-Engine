"use client";

import {
  Check,
  Copy,
  Download,
  FileImage,
  FileText,
  FileVideo,
  Presentation,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";

const tabs = [
  { label: "Executive Summary", icon: FileText },
  { label: "Presentation", icon: Presentation },
  { label: "LinkedIn Post", icon: FileText },
  { label: "Twitter/X", icon: FileText },
  { label: "Advisory", icon: FileText },
  { label: "Infographic", icon: FileImage },
  { label: "Video Package", icon: FileVideo },
];

export default function GeneratedOutputPage() {
  const [activeTab, setActiveTab] = useState(tabs[0].label);
  const [copied, setCopied] = useState(false);
  const [version, setVersion] = useState(3);

  const copyContent = async () => {
    await navigator.clipboard?.writeText("The Digital Public Services Programme has made steady progress across citizen-facing departments.");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <main className="relay-shell">
      <AppSidebar />
      <section className="relay-main">
        <header className="relay-topbar">
          <div className="relay-breadcrumb"><span>relay</span><span>/</span><span>history</span><span>/</span><strong>run_2025_0148</strong></div>
          <div className="relay-top-actions"><span className="relay-status"><i /> run complete</span><span className="relay-command">⌘ K</span><div className="relay-avatar">AI</div></div>
        </header>

        <div className="relay-history-content">
          <div className="relay-history-heading">
            <div><p className="relay-kicker">history / run_2025_0148</p><h1>Digital services programme</h1><p>Generated output · version {version} · completed today at 10:42</p></div>
            <span className="relay-history-status"><i /> ready for review</span>
          </div>

          <div className="relay-history-layout">
            <section className="relay-generated-panel">
              <div className="relay-generated-toolbar">
                <div className="relay-generated-file"><FileText size={15} /><span>{activeTab.toLowerCase().replaceAll(" ", "_")}.md</span></div>
                <div className="relay-generated-actions">
                  <button type="button" onClick={copyContent}>{copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "copied" : "copy"}</button>
                  <button type="button"><Download size={13} /> export</button>
                  <button type="button" onClick={() => setVersion((current) => current + 1)}><RefreshCw size={13} /> regenerate</button>
                </div>
              </div>
              <div className="relay-history-tabs" role="tablist" aria-label="Generated outputs">
                {tabs.map(({ label, icon: Icon }) => <button className={activeTab === label ? "active" : ""} key={label} type="button" role="tab" aria-selected={activeTab === label} onClick={() => setActiveTab(label)}><Icon size={13} />{label}</button>)}
              </div>
              <article className="relay-generated-document">
                <span className="relay-document-eyebrow">generated / {activeTab.toLowerCase()}</span>
                <h2>{activeTab}</h2>
                <div className="relay-doc-rule" />
                <p>The Ministry&apos;s Digital Public Services Programme has made steady progress across citizen-facing departments, with 68% of priority services now available online.</p>
                <p>The next phase should focus on improving adoption in rural districts, strengthening accessibility standards, and establishing a consistent measurement framework across departments.</p>
                <h3>Key observations</h3>
                <ul>
                  <li>Online availability has expanded across priority services.</li>
                  <li>Adoption remains uneven across regions.</li>
                  <li>Accessibility and measurement are the next operational priorities.</li>
                </ul>
                <div className="relay-generated-footer"><span>source-grounded output</span><span>review status: pending</span></div>
              </article>
            </section>

            <aside className="relay-history-sidebar">
              <div className="relay-panel relay-metadata-panel">
                <div className="relay-panel-header"><div><span className="relay-index">metadata</span><h2>Generation details</h2></div></div>
                <div className="relay-source-file"><FileText size={14} /><span>digital-services-programme.docx</span></div>
                <div className="relay-history-metadata">
                  <div><span>source file</span><strong>digital-services-programme.docx</strong></div>
                  <div><span>audience</span><strong>Executive</strong></div>
                  <div><span>tone</span><strong>Formal</strong></div>
                  <div><span>language</span><strong>English</strong></div>
                  <div><span>generation time</span><strong>Today, 10:42</strong></div>
                </div>
              </div>
              <div className="relay-panel relay-history-version-panel">
                <div className="relay-panel-header"><div><span className="relay-index">versions</span><h2>Version history</h2></div></div>
                <div className="relay-history-version active"><span>v{version}</span><div><strong>Current output</strong><small>ready for review</small></div></div>
                <div className="relay-history-version"><span>v2</span><div><strong>Audience updated</strong><small>2 minutes ago</small></div></div>
                <div className="relay-history-version"><span>v1</span><div><strong>Initial generation</strong><small>4 minutes ago</small></div></div>
              </div>
            </aside>
          </div>
        </div>
      </section>
    </main>
  );
}
