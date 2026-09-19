"use client";

import { Eye, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ArtefactPreview } from "@/components/artefact-previews";
import { previewUrl } from "@/lib/api";
import type { Draft } from "@/lib/types";

/**
 * Preview a rendered file, the way a print preview works.
 *
 * Uses the *preview* endpoint rather than the download endpoint on purpose: the
 * download route sends `Content-Disposition: attachment`, which makes a browser
 * refuse to render the content — an <iframe> pointed at it shows a blank page.
 * The preview route sends `inline`, so PDFs and images display properly, and it
 * works before approval because it renders straight from the draft.
 */

const TEXT_EXTS = new Set(["md", "txt", "json", "srt"]);

/** Formats we can show something meaningful for. */
export function isPreviewable(ext: string): boolean {
  return ext === "png" || ext === "pdf" || ext === "pptx" || TEXT_EXTS.has(ext);
}

function FileBody({
  threadId, type, ext, draft,
}: { threadId: string; type: string; ext: string; draft?: Draft }) {
  const url = previewUrl(threadId, type, ext);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!TEXT_EXTS.has(ext)) return;
    let cancelled = false;
    fetch(url)
      .then((response) => (response.ok ? response.text() : Promise.reject(new Error(String(response.status)))))
      .then((body) => { if (!cancelled) setText(body); })
      .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : "failed to load"); });
    return () => { cancelled = true; };
  }, [url, ext]);

  if (ext === "png") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="pv-image" src={url} alt={`${type} poster`} />;
  }

  if (ext === "pdf") {
    return <iframe className="pv-frame" src={url} title={`${type} preview`} />;
  }

  // No browser renders PowerPoint, so show the deck's actual content instead of
  // a blank frame: the same slide breakdown used on the artefact tab.
  if (ext === "pptx") {
    if (!draft) return <p className="pv-error">The slide breakdown is unavailable for this run.</p>;
    return <ArtefactPreview type={type} draft={draft} threadId={threadId} />;
  }

  if (TEXT_EXTS.has(ext)) {
    if (error) return <p className="pv-error">Could not load preview ({error}).</p>;
    if (text === null) return <p className="pv-loading">Loading…</p>;
    return <pre className="pv-text">{text}</pre>;
  }

  return <p className="pv-error">No preview available for .{ext} — download it to open it.</p>;
}

export function FilePreview({
  threadId, type, ext, label, draft,
}: { threadId: string; type: string; ext: string; label?: string; draft?: Draft }) {
  const [open, setOpen] = useState(false);

  if (!isPreviewable(ext)) return null;

  return (
    <>
      <button
        className="pv-eye"
        type="button"
        title={`Preview ${type}.${ext}`}
        aria-label={`Preview ${type}.${ext}`}
        onClick={() => setOpen(true)}
      >
        <Eye size={13} />
      </button>

      {open ? (
        <div className="pv-overlay" role="dialog" aria-modal="true" onClick={() => setOpen(false)}>
          <div className="pv-modal" onClick={(event) => event.stopPropagation()}>
            <div className="pv-head">
              <span className="pv-title">{label ?? `${type}.${ext}`}</span>
              <button className="pv-close" type="button" onClick={() => setOpen(false)} aria-label="Close preview">
                <X size={15} />
              </button>
            </div>
            <div className="pv-body">
              <FileBody threadId={threadId} type={type} ext={ext} draft={draft} />
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
