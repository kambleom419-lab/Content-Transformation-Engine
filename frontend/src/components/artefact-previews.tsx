"use client";

import { previewUrl } from "@/lib/api";
import { fieldLabel, type Draft } from "@/lib/types";

/**
 * Per-artefact previews.
 *
 * Deliberately NOT pixel-perfect clones of LinkedIn or X — imitating another
 * product's chrome looks cheap. These are clean, readable representations: the
 * shape of the deliverable, so an operator can judge it at a glance.
 */

const LIST_FIELDS = new Set([
  "affected_systems", "iocs", "mitigations", "references", "key_points",
  "recommendations", "hashtags", "tweets", "storyboard", "scene_descriptions",
  "subtitles", "visual_recommendations", "content", "layout_recommendations",
  "key_messaging", "key_messages", "bullets",
]);

const SEVERITY_CLASS: Record<string, string> = {
  critical: "ap-pill critical",
  high: "ap-pill high",
  medium: "ap-pill medium",
  low: "ap-pill low",
  info: "ap-pill info",
};

function toItems(value: unknown): string[] {
  if (value === null || value === undefined) return [];
  if (typeof value === "string") return value.trim() ? [value] : [];
  if (Array.isArray(value)) {
    return value.flatMap((entry) => {
      if (typeof entry === "string") return entry.trim() ? [entry] : [];
      if (entry && typeof entry === "object") {
        const text = Object.values(entry as Record<string, unknown>).filter(Boolean).join(" — ");
        return text.trim() ? [text] : [];
      }
      return [];
    });
  }
  return [String(value)];
}

function asText(value: unknown): string {
  return toItems(value).join("\n\n");
}

function entriesOf(draft: Draft, skip: string[] = []): [string, unknown][] {
  return Object.entries(draft).filter(([field]) => !skip.includes(field));
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="ap-section">
      <h4 className="ap-section-title">{title}</h4>
      {children}
    </div>
  );
}

/** Document layout — used by advisory and executive_summary. */
function DocumentPreview({ draft, severity }: { draft: Draft; severity?: string }) {
  return (
    <div className="ap ap-doc">
      {severity ? <span className={SEVERITY_CLASS[severity] ?? "ap-pill"}>{severity}</span> : null}
      {entriesOf(draft).map(([field, value]) => {
        const items = toItems(value);
        if (!items.length) return null;
        const isList = LIST_FIELDS.has(field) || items.length > 1;

        return (
          <Section key={field} title={fieldLabel(field)}>
            {field === "iocs" ? (
              <div className="ap-chips">
                {items.map((item, index) => <code className="ap-chip" key={index}>{item}</code>)}
              </div>
            ) : isList ? (
              <ul className="ap-list">{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
            ) : (
              <p className="ap-p">{items[0]}</p>
            )}
          </Section>
        );
      })}
    </div>
  );
}

/** A plain post card — LinkedIn / any social body. */
function PostPreview({ draft }: { draft: Draft }) {
  const headline = toItems(draft.headline ?? draft.title)[0] ?? "";
  const body = asText(draft.body ?? draft.summary ?? draft.content);
  const cta = toItems(draft.cta)[0];
  const hashtags = toItems(draft.hashtags);

  return (
    <div className="ap">
      <div className="ap-post">
        <div className="ap-post-tag">post preview</div>
        {headline ? <h3 className="ap-post-headline">{headline}</h3> : null}
        {body ? <p className="ap-post-body">{body}</p> : null}
        {cta ? <p className="ap-post-cta">{cta}</p> : null}
        {hashtags.length ? (
          <div className="ap-hashtags">
            {hashtags.map((tag, index) => (
              <span key={index}>{tag.startsWith("#") ? tag : `#${tag}`}</span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** A simple thread — numbered entries with a character count, no fake chrome. */
function ThreadPreview({ draft }: { draft: Draft }) {
  const tweets = toItems(draft.tweets);
  const total = tweets.length;

  return (
    <div className="ap ap-thread">
      {tweets.map((tweet, index) => (
        <div className="ap-tweet" key={index}>
          <div className="ap-tweet-rail">
            <span className="ap-tweet-num">{index + 1}</span>
            {index < total - 1 ? <span className="ap-tweet-line" /> : null}
          </div>
          <div className="ap-tweet-body">
            <p>{tweet}</p>
            <div className="ap-tweet-meta">
              <span>{index + 1} / {total}</span>
              <span className={tweet.length > 280 ? "over" : ""}>{tweet.length} / 280</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Slide list — each slide as a 16:9 frame, with the speaking note beside it. */
function SlidesPreview({ draft }: { draft: Draft }) {
  const slides = Array.isArray(draft.slides) ? (draft.slides as Record<string, unknown>[]) : [];

  return (
    <div className="ap ap-slides">
      {slides.map((slide, index) => (
        <div className="ap-slide-card" key={index}>
          <div className="ap-slide-frame">
            <div className="ap-slide-frame-inner">
              <span className="ap-slide-eyebrow">{String(index + 1).padStart(2, "0")}</span>
              <h4>{String(slide.title ?? `Slide ${index + 1}`)}</h4>
              <span className="ap-slide-rule" />
              {toItems(slide.bullets).length ? (
                <ul>
                  {toItems(slide.bullets).map((bullet, i) => <li key={i}>{bullet}</li>)}
                </ul>
              ) : null}
            </div>
          </div>
          {slide.speaker_notes ? (
            <div className="ap-slide-notes">
              <span className="ap-notes-label">speaker note</span>
              {String(slide.speaker_notes)}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** Video package — script, storyboard scenes, narration, subtitles. */
function VideoPreview({ draft }: { draft: Draft }) {
  const script = asText(draft.script);
  const storyboard = toItems(draft.storyboard);
  const scenes = toItems(draft.scene_descriptions);
  const narration = asText(draft.narration);
  const subtitles = toItems(draft.subtitles);
  const visuals = toItems(draft.visual_recommendations);

  return (
    <div className="ap ap-video">
      {script ? <Section title="Script"><p className="ap-p">{script}</p></Section> : null}

      {storyboard.length ? (
        <Section title="Storyboard">
          <div className="ap-scenes">
            {storyboard.map((scene, index) => (
              <div className="ap-scene" key={index}>
                <span className="ap-scene-num">{String(index + 1).padStart(2, "0")}</span>
                <span className="ap-scene-text">{scene}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {scenes.length ? (
        <Section title="Scene descriptions">
          <ul className="ap-list">{scenes.map((scene, index) => <li key={index}>{scene}</li>)}</ul>
        </Section>
      ) : null}

      {narration ? <Section title="Narration"><p className="ap-p">{narration}</p></Section> : null}

      {subtitles.length ? (
        <Section title="Subtitles">
          <div className="ap-subs">
            {subtitles.map((cue, index) => (
              <div className="ap-sub" key={index}>
                <span className="ap-sub-index">{String(index + 1).padStart(2, "0")}</span>
                <span>{cue}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {visuals.length ? (
        <Section title="Visual recommendations">
          <ul className="ap-list">{visuals.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </Section>
      ) : null}
    </div>
  );
}

/**
 * Infographic — the real rendered poster.
 *
 * Uses the preview endpoint, which renders on demand, so the poster is visible
 * while the run is still paused for review rather than only after approval.
 */
function InfographicPreview({ threadId }: { threadId: string }) {
  return (
    <div className="ap ap-poster">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={previewUrl(threadId, "infographic", "png")} alt="Infographic poster" />
      <div className="ap-poster-meta">
        <span>poster preview</span>
        <span>rendered live · updates as you refine</span>
      </div>
    </div>
  );
}

export function ArtefactPreview({
  type, draft, threadId, severity,
}: {
  type: string;
  draft: Draft;
  threadId: string;
  severity?: string;
}) {
  if (!draft || !Object.keys(draft).length) {
    return <p className="ap-empty">No artefact for this output yet.</p>;
  }

  switch (type) {
    case "linkedin_post":
      return <PostPreview draft={draft} />;
    case "x_thread":
      return <ThreadPreview draft={draft} />;
    case "presentation":
      return <SlidesPreview draft={draft} />;
    case "video_package":
      return <VideoPreview draft={draft} />;
    case "infographic":
      return <InfographicPreview threadId={threadId} />;
    default:
      return <DocumentPreview draft={draft} severity={severity} />;
  }
}
