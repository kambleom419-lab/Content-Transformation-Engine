"use client";

import { AppSidebar } from "@/components/app-sidebar";
import { ChevronDown, Check } from "lucide-react";
import { useState } from "react";

export default function SettingsPage() {
  const [multiple, setMultiple] = useState(true);
  const [summaries, setSummaries] = useState(true);
  const [versions, setVersions] = useState(true);
  const toggle = (label: string, enabled: boolean, setEnabled: (value: boolean) => void) => <button className={`settings-toggle ${enabled ? "enabled" : ""}`} type="button" aria-label={`${label}: ${enabled ? "enabled" : "disabled"}`} aria-pressed={enabled} onClick={() => setEnabled(!enabled)}><span>{enabled ? <Check size={11} /> : ""}</span></button>;

  return (
    <main className="dashboard-shell">
      <AppSidebar />
      <section className="main-area">
        <header className="workspace-topbar"><div className="workspace-breadcrumb"><span>relay</span><span>/</span><strong>settings</strong></div><span className="workspace-topbar-status">workspace online</span></header>
        <div className="workspace-page settings-page">
          <div className="workspace-page-heading"><div><p className="workspace-kicker">workspace / settings</p><h1>Settings</h1><p>Workspace configuration.</p></div><span className="workspace-page-meta">last saved just now</span></div>
          <div className="settings-grid">
            <section className="workspace-card settings-card"><div className="section-card-heading"><div><span className="workspace-kicker">workspace</span><h2>Workspace</h2></div></div><div className="settings-rows"><div><span>Name</span><strong>Relay</strong></div><div><span>Environment</span><strong>Secure Government Workspace</strong></div></div></section>
            <section className="workspace-card settings-card"><div className="section-card-heading"><div><span className="workspace-kicker">generation defaults</span><h2>Generation Defaults</h2></div></div><div className="settings-rows"><label><span>Language</span><div className="settings-select"><select defaultValue="English"><option>English</option><option>Hindi</option><option>Regional Language</option></select><ChevronDown size={14} /></div></label><label><span>Tone</span><div className="settings-select"><select defaultValue="Formal"><option>Formal</option><option>Professional</option><option>Technical</option></select><ChevronDown size={14} /></div></label><label><span>Audience</span><div className="settings-select"><select defaultValue="Government Officials"><option>Government Officials</option><option>Citizens</option><option>Executive Leadership</option></select><ChevronDown size={14} /></div></label></div></section>
            <section className="workspace-card settings-card"><div className="section-card-heading"><div><span className="workspace-kicker">output preferences</span><h2>Output Preferences</h2></div></div><div className="settings-rows settings-options"><div><span>Enable Multiple Deliverables</span>{toggle("multiple deliverables", multiple, setMultiple)}</div><div><span>Enable Auto Summaries</span>{toggle("auto summaries", summaries, setSummaries)}</div><div><span>Enable Version History</span>{toggle("version history", versions, setVersions)}</div></div></section>
            <section className="workspace-card settings-card"><div className="section-card-heading"><div><span className="workspace-kicker">security</span><h2>Security</h2></div><span className="status-badge active">protected</span></div><div className="settings-rows settings-options"><div><span>Workspace Encryption Enabled</span><span className="settings-confirmed"><Check size={13} /> Enabled</span></div><div><span>Audit Logs Enabled</span><span className="settings-confirmed"><Check size={13} /> Enabled</span></div></div></section>
          </div>
        </div>
      </section>
    </main>
  );
}
