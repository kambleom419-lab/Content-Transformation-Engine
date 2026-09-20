"use client";

import { Check, Eye, X } from "lucide-react";
import { useEffect, useState } from "react";
import { listTemplates, templatePreviewUrl, type TemplateOption } from "@/lib/api";

/**
 * Template chooser.
 *
 * Each card shows a real render of the template with placeholder content, so the
 * operator is choosing from what they can see rather than from a colour swatch.
 * The eye opens it full size.
 */
export function TemplatePicker({
  value, onChange,
}: { value: string; onChange: (key: string) => void }) {
  const [templates, setTemplates] = useState<TemplateOption[]>([]);
  const [zoomed, setZoomed] = useState<TemplateOption | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listTemplates()
      .then((data) => setTemplates(data.templates))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "could not load templates"));
  }, []);

  if (error) return <p className="tp-note tp-error">{error}</p>;
  if (!templates.length) return <p className="tp-note">Loading templates…</p>;

  return (
    <div className="tp">
      <div className="tp-grid">
        {templates.map((template) => {
          const active = template.key === value;
          return (
            <div className={`tp-card ${active ? "is-active" : ""}`} key={template.key}>
              <button
                type="button"
                className="tp-preview"
                onClick={() => onChange(template.key)}
                aria-pressed={active}
                title={`Use the ${template.label} template`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={templatePreviewUrl(template.preview)} alt={`${template.label} template`} />
                <span className="tp-mark">{active ? <Check size={12} /> : null}</span>
              </button>

              <div className="tp-meta">
                <strong>{template.label}</strong>
                <small>{template.blurb}</small>
              </div>

              <button
                type="button"
                className="tp-eye"
                onClick={() => setZoomed(template)}
                aria-label={`Preview ${template.label} full size`}
                title="Preview full size"
              >
                <Eye size={13} />
              </button>
            </div>
          );
        })}
      </div>

      {zoomed ? (
        <div className="tp-overlay" role="dialog" aria-modal="true" onClick={() => setZoomed(null)}>
          <div className="tp-zoom" onClick={(event) => event.stopPropagation()}>
            <div className="tp-zoom-head">
              <span>{zoomed.label} — sample render</span>
              <button type="button" onClick={() => setZoomed(null)} aria-label="Close preview">
                <X size={15} />
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={templatePreviewUrl(zoomed.preview)} alt={`${zoomed.label} template`} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
