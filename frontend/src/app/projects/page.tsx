import { AppSidebar } from "@/components/app-sidebar";
import { FolderKanban, Search } from "lucide-react";

export default function ProjectsPage() {
  const projects = [
    ["National Cyber Advisory Campaign", "Active", "42", "2 hours ago"],
    ["Public Health Awareness Initiative", "Active", "28", "Today"],
    ["Monsoon Preparedness Communication", "Completed", "35", "Yesterday"],
    ["Digital Services Modernization Programme", "Draft", "12", "3 days ago"],
  ];

  return (
    <main className="dashboard-shell">
      <AppSidebar />
      <section className="main-area">
        <header className="workspace-topbar"><div className="workspace-breadcrumb"><span>relay</span><span>/</span><strong>projects</strong></div><span className="workspace-topbar-status">workspace online</span></header>
        <div className="workspace-page">
          <div className="workspace-page-heading"><div><p className="workspace-kicker">workspace / projects</p><h1>Projects</h1><p>Manage content transformation initiatives and deliverables.</p></div><button className="workspace-primary-button" type="button"><FolderKanban size={15} /> New project</button></div>
          <div className="workspace-toolbar"><label className="workspace-search"><Search size={16} /><input placeholder="Search projects" aria-label="Search projects" /></label><span className="workspace-result-count">4 projects</span></div>
          <div className="project-grid">{projects.map(([name, status, outputs, activity]) => <article className="workspace-card project-card" key={name}><div className="workspace-card-top"><span className={`status-badge ${status.toLowerCase()}`}>{status}</span><span className="workspace-card-index">project</span></div><h2>{name}</h2><div className="project-stat"><span>generated outputs</span><strong>{outputs}</strong></div><div className="project-stat"><span>last activity</span><strong>{activity}</strong></div><div className="project-card-footer"><span>Open project</span><span>→</span></div></article>)}</div>
        </div>
      </section>
    </main>
  );
}
