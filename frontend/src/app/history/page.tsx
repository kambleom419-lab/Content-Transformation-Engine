import { AppSidebar } from "@/components/app-sidebar";
import { FileText } from "lucide-react";

export default function HistoryPage() {
  const entries = [
    ["10:42 AM", "Executive Summary generated", "digital-services-programme.docx", "Completed"],
    ["10:45 AM", "LinkedIn Post generated", "digital-services-programme.docx", "Completed"],
    ["10:47 AM", "Presentation generated", "national-cyber-advisory.pdf", "Completed"],
    ["10:48 AM", "Video Script generated", "national-cyber-advisory.pdf", "Completed"],
    ["11:05 AM", "Government Advisory generated", "monsoon-preparedness-notes.docx", "Completed"],
    ["11:12 AM", "Twitter/X Thread generated", "public-health-briefing.pdf", "Review"],
  ];

  return (
    <main className="dashboard-shell">
      <AppSidebar />
      <section className="main-area">
        <header className="workspace-topbar"><div className="workspace-breadcrumb"><span>relay</span><span>/</span><strong>history</strong></div><span className="workspace-topbar-status">workspace online</span></header>
        <div className="workspace-page">
          <div className="workspace-page-heading"><div><p className="workspace-kicker">workspace / history</p><h1>History</h1><p>Review previous content transformation runs.</p></div><span className="workspace-page-meta">18 runs this month</span></div>
          <section className="workspace-card history-card"><div className="section-card-heading"><div><span className="workspace-kicker">recent activity</span><h2>Transformation timeline</h2></div><span className="workspace-card-index">latest first</span></div><div className="history-list">{entries.map(([time, title, source, status]) => <div className="history-item" key={`${time}-${title}`}><div className="history-time">{time}</div><div className="history-marker"><span /></div><div className="history-copy"><strong>{title}</strong><span><FileText size={13} /> {source}</span></div><span className={`status-badge ${status.toLowerCase()}`}>{status}</span></div>)}</div></section>
        </div>
      </section>
    </main>
  );
}
