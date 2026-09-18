"use client";

import {
  ChevronDown,
  FileText,
  Folder,
  History,
  LayoutDashboard,
  Menu,
  MoreHorizontal,
  Settings,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const navItems = [
  { label: "Workspace", href: "/dashboard", icon: LayoutDashboard },
  { label: "Transformations", href: "/projects", icon: Folder },
  { label: "Templates", href: "/templates", icon: FileText },
  { label: "Review Queue", href: "/review", icon: History },
  { label: "Activity", href: "/history", icon: History },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      <button
        className="mobile-menu-trigger"
        type="button"
        aria-label="Open navigation"
        onClick={() => setMobileOpen(true)}
      >
        <Menu size={18} />
      </button>
      {mobileOpen && (
        <button
          className="sidebar-overlay"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">R</div>
          <span>Relay</span>
          <button className="sidebar-close" type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)}>
            <X size={17} />
          </button>
        </div>
        <button className="workspace-switcher" type="button">
          <span className="workspace-avatar">G</span>
          <span className="workspace-name">internal / comms</span>
          <ChevronDown size={14} />
        </button>
        <nav className="primary-nav" aria-label="Main navigation">
          <span className="nav-heading">Workspace</span>
          {navItems.map(({ label, href, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                className={`nav-item ${active ? "active" : ""}`}
                href={href}
                key={href}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={16} strokeWidth={1.8} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-note">
            <div className="sidebar-note-title">system status</div>
            <div className="status-line"><span className="status-dot" /> operational</div>
          </div>
          <div className="profile-row">
            <div className="profile-avatar">AS</div>
            <div className="profile-copy"><strong>Arvind Iyer</strong><small>Administrator</small></div>
            <MoreHorizontal size={15} />
          </div>
        </div>
      </aside>
    </>
  );
}
