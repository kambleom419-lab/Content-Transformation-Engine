import { AppSidebar } from "@/components/app-sidebar";
import { FileText } from "lucide-react";

export default function TemplatesPage() {
  const templates = [
    ["Executive Summary", "Decision-ready brief for senior review.", "Executive leadership", "Formal"],
    ["Government Advisory", "Clear guidance for public distribution.", "Citizens and stakeholders", "Authoritative"],
    ["Citizen Awareness Campaign", "Accessible messaging for public programmes.", "General public", "Clear"],
    ["LinkedIn Post", "Professional update for institutional channels.", "Professional audience", "Professional"],
    ["Twitter/X Thread", "Concise multi-post narrative for timely updates.", "Digital audience", "Direct"],
    ["Presentation Deck", "Structured slide outline for briefings.", "Internal teams", "Executive"],
    ["Press Release", "Publish-ready announcement for media desks.", "Journalists and media", "Formal"],
    ["Video Script Package", "Script, scenes, and narration for production.", "Public information teams", "Conversational"],
  ];

  return (
    <main className="dashboard-shell">
      <AppSidebar />
      <section className="main-area">
        <header className="workspace-topbar"><div className="workspace-breadcrumb"><span>relay</span><span>/</span><strong>templates</strong></div><span className="workspace-topbar-status">workspace online</span></header>
        <div className="workspace-page">
          <div className="workspace-page-heading"><div><p className="workspace-kicker">workspace / templates</p><h1>Templates</h1><p>Reusable communication blueprints.</p></div><button className="workspace-primary-button" type="button"><FileText size={15} /> New template</button></div>
          <div className="template-grid">{templates.map(([name, description, audience, tone], index) => <article className="workspace-card template-card" key={name}><div className="workspace-card-top"><span className="template-number">{String(index + 1).padStart(2, "0")}</span><FileText size={17} /></div><h2>{name}</h2><p>{description}</p><div className="template-meta"><div><span>audience</span><strong>{audience}</strong></div><div><span>tone</span><strong>{tone}</strong></div></div></article>)}</div>
        </div>
      </section>
    </main>
  );
}
