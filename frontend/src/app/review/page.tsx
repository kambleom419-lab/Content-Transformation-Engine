import { AppSidebar } from "@/components/app-sidebar";
import { AlertCircle, CheckCircle2, Clock3, FileText } from "lucide-react";

const reviewItems = [
  ["Public Health Briefing", "Executive Summary · Advisory", "12 min ago", "Pending Review"],
  ["National Cyber Advisory", "Presentation · Infographic", "Yesterday", "Approved"],
  ["Digital Services Programme", "LinkedIn Post · X Thread", "2 days ago", "Needs Changes"],
];

export default function ReviewPage() {
  return (
    <main className="dashboard-shell">
      <AppSidebar />
      <section className="main-area">
        <header className="workspace-topbar"><div className="workspace-breadcrumb"><span>relay</span><span>/</span><strong>review queue</strong></div><span className="workspace-topbar-status">workspace online</span></header>
        <div className="workspace-page review-page">
          <div className="workspace-page-heading"><div><p className="workspace-kicker">workspace / review queue</p><h1>Review Queue</h1><p>Inspect generated deliverables before they move to export.</p></div><span className="workspace-page-meta">3 items requiring attention</span></div>
          <div className="review-summary-grid">
            <div className="workspace-card review-summary-card"><Clock3 size={18} /><strong>1</strong><span>Pending review</span></div>
            <div className="workspace-card review-summary-card"><CheckCircle2 size={18} /><strong>1</strong><span>Approved</span></div>
            <div className="workspace-card review-summary-card"><AlertCircle size={18} /><strong>1</strong><span>Needs changes</span></div>
          </div>
          <section className="workspace-card review-list-card">
            <div className="section-card-heading"><div><span className="workspace-kicker">human-in-the-loop</span><h2>Deliverables awaiting decisions</h2></div><span className="workspace-card-index">latest first</span></div>
            <div className="review-list">{reviewItems.map(([title, outputs, time, status]) => <article className="review-item" key={title}><div className="review-item-icon"><FileText size={18} /></div><div className="review-item-copy"><strong>{title}</strong><span>{outputs}</span></div><time>{time}</time><span className={`status-badge ${status.toLowerCase().replaceAll(" ", "-")}`}>{status}</span><button type="button" className="workspace-secondary-button">Open review</button></article>)}</div>
          </section>
        </div>
      </section>
    </main>
  );
}
