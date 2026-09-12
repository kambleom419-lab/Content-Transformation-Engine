"use client";

import { ArrowRight, FileText, Menu, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AntigravityBackground } from "@/components/antigravity-background";
import { StarsBackground } from "@/components/animate-ui/components/backgrounds/stars";

export default function LandingPage() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <main className="relay-landing">
      <div className="absolute inset-0 -z-10 pointer-events-none opacity-30">
    
  </div>
      <header className="relay-landing-nav">
        <Link href="/" className="relay-landing-brand">
          <span className="relay-landing-mark">R</span>
          <span>Relay</span>
        </Link>
        <nav className={`relay-landing-links ${mobileOpen ? "open" : ""}`} aria-label="Landing navigation">
          <a href="#capabilities" onClick={() => setMobileOpen(false)}>Capabilities</a>
          <a href="#security" onClick={() => setMobileOpen(false)}>Security</a>
          <a href="#about" onClick={() => setMobileOpen(false)}>About</a>
          <Link href="/dashboard" className="relay-mobile-cta" onClick={() => setMobileOpen(false)}>Open workspace <ArrowRight size={13} /></Link>
        </nav>
        <div className="relay-landing-actions">
          <Link href="/dashboard" className="relay-landing-signin">Sign in</Link>
          <Link href="/dashboard" className="relay-landing-nav-button">Open workspace <ArrowRight size={13} /></Link>
        </div>
        <button className="relay-landing-menu" type="button" aria-label="Toggle navigation" onClick={() => setMobileOpen((open) => !open)}>
          {mobileOpen ? <X size={17} /> : <Menu size={17} />}
        </button>
      </header>

      <section className="relay-landing-hero">
        <div className="relay-landing-hero-content">
          <div className="relay-landing-eyebrow"><span /> secure content operations</div>
          <h1>One Source.<br /><span>Multiple Deliverables.</span></h1>
          <p>Transform documents, reports, advisories, research papers, articles, prompts, images and videos into presentations, executive summaries, advisories, social content and video packages.</p>
          <div className="relay-landing-hero-actions">
            <Link href="/dashboard" className="relay-landing-primary">Start Transformation <ArrowRight size={15} /></Link>
            <a href="#demo" className="relay-landing-secondary"><span className="relay-play">▶</span> View Demo</a>
          </div>
          <div className="relay-landing-trust"><ShieldCheck size={14} /><span>Private workspace</span><i /> <span>Reviewable outputs</span><i /> <span>Built for sensitive work</span></div>
        </div>
        <div className="relay-landing-scroll"><span>01</span><span>source material → shared understanding</span><div /></div>
      </section>

      <section className="relay-landing-section" id="capabilities">
        <div className="relay-landing-section-heading"><span>01 / capabilities</span><h2>One source of truth<br /><em>for every channel.</em></h2><p>Relay keeps the original context intact while preparing the formats your teams need to move work forward.</p></div>
        <div className="relay-landing-capability-grid">
          <div><span>01</span><FileText size={17} /><h3>Understand the source</h3><p>Make long reports, briefings, and research easier to navigate without losing the details that matter.</p></div>
          <div><span>02</span><FileText size={17} /><h3>Prepare every deliverable</h3><p>Move from source material to presentations, advisories, summaries, and publish-ready content.</p></div>
          <div><span>03</span><ShieldCheck size={17} /><h3>Keep review in the loop</h3><p>Give teams a clear, inspectable result before anything is shared externally.</p></div>
        </div>
      </section>

      <section className="relay-landing-section relay-landing-security" id="security">
        <div><span>02 / operating principle</span><h2>Clarity without<br /><em>losing control.</em></h2></div>
        <div className="relay-landing-principles"><div><strong>01</strong><span>Source-grounded</span><p>Outputs stay anchored to the material your team provides.</p></div><div><strong>02</strong><span>Workspace-private</span><p>Keep consequential work within your organization’s controlled environment.</p></div><div><strong>03</strong><span>Human-reviewed</span><p>Every deliverable is designed to be read, checked, and refined.</p></div></div>
      </section>

      <section className="relay-landing-final" id="about"><span>relay / workspace</span><h2>Make the next step<br />obvious.</h2><Link href="/dashboard" className="relay-landing-primary">Start Transformation <ArrowRight size={15} /></Link></section>
      <footer className="relay-landing-footer"><Link href="/" className="relay-landing-brand"><span className="relay-landing-mark">R</span><span>Relay</span></Link><span>One Source. Multiple Deliverables.</span><span>Internal platform</span></footer>
    </main>
  );
}
