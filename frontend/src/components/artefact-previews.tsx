"use client";

import { BadgeCheck, Bookmark, Check, Copy, ExternalLink, Eye, Heart, MessageCircle, MoreHorizontal, Repeat2, Share } from "lucide-react";
import { useState } from "react";
import { previewUrl } from "@/lib/api";
import { fieldLabel, type Draft } from "@/lib/types";

/**
 * The identity shown on social previews. Edit here to change it everywhere —
 * a preview is far more useful when it looks like a post this operator would
 * actually publish.
 */
const POST_AUTHOR = {
  name: "Om Kamble",
  headline: "SIH 2026 · Content Transformation Engine",
  handle: "OmKamble49012",
  avatar: "https://avatars.githubusercontent.com/u/239809590?v=4",
};

const LINKEDIN_LIMIT = 3000;
const X_LIMIT = 280;

function Avatar({ size = 40 }: { size?: number }) {
  const [broken, setBroken] = useState(false);
  const initials = POST_AUTHOR.name.split(" ").map((part) => part[0]).join("");

  if (broken) {
    return (
      <span className="sp-avatar sp-avatar-fallback" style={{ width: size, height: size, fontSize: size / 2.6 }}>
        {initials}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className="sp-avatar"
      src={POST_AUTHOR.avatar}
      alt={POST_AUTHOR.name}
      width={size}
      height={size}
      onError={() => setBroken(true)}
    />
  );
}

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

/** A LinkedIn-style post: who posted it, the post itself, and its limits. */
function PostPreview({ draft }: { draft: Draft }) {
  const headline = toItems(draft.headline ?? draft.title)[0] ?? "";
  const body = asText(draft.body ?? draft.summary ?? draft.content);
  const cta = toItems(draft.cta)[0];
  const hashtags = toItems(draft.hashtags);
  const characters = [headline, body, cta].filter(Boolean).join("\n\n").length;
  const over = characters > LINKEDIN_LIMIT;

  return (
    <div className="ap">
      <article className="sp-post">
        <header className="sp-head">
          <Avatar />
          <div className="sp-who">
            <strong>{POST_AUTHOR.name}</strong>
            <span>{POST_AUTHOR.headline}</span>
            <span className="sp-when">now · visible to anyone</span>
          </div>
          <span className="sp-channel">in</span>
        </header>

        <div className="sp-body">
          {headline ? <h3>{headline}</h3> : null}
          {body ? <p><RichText text={body} /></p> : null}
          {cta ? <p className="sp-cta">{cta}</p> : null}
          {hashtags.length ? (
            <div className="sp-tags">
              {hashtags.map((tag, index) => (
                <span key={index}>{tag.startsWith("#") ? tag : `#${tag}`}</span>
              ))}
            </div>
          ) : null}
        </div>

        <footer className="sp-foot">
          <span>{characters.toLocaleString()} / {LINKEDIN_LIMIT.toLocaleString()} characters</span>
          <span className={over ? "over" : "ok"}>{over ? "over the limit" : "within limit"}</span>
        </footer>
      </article>
    </div>
  );
}

/** Copy helper — the practical half of "hand this to the platform". */
function CopyToClipboard({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="x-copy"
      onClick={async () => {
        await navigator.clipboard?.writeText(text);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      }}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : label}
    </button>
  );
}

/** Highlights #hashtags and @mentions the way the platforms do. */
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\s+)/).map((part, index) =>
        /^[#@][\w-]+$/.test(part) ? (
          <span className="x-link" key={index}>{part}</span>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

/**
 * An X post.
 *
 * Rendered as ONE post, the way X shows a post: avatar, name, verified tick,
 * handle, menu, body, action row. A thread draft is represented by its opening
 * post, with the remaining posts stated underneath rather than stacked as more
 * cards — the full thread always exists in the exported .txt.
 *
 * Engagement counts are deliberately absent. This is an unpublished draft, and
 * inventing "39K likes" would misrepresent it.
 */
function ThreadPreview({ draft }: { draft: Draft }) {
  const tweets = toItems(draft.tweets);
  const post = tweets[0] ?? "";
  const remaining = Math.max(0, tweets.length - 1);
  const over = post.length > X_LIMIT;

  return (
    <div className="ap">
      <article className="x-post">
        <div className="x-rail">
          <Avatar size={40} />
        </div>

        <div className="x-main">
          <header className="x-head">
            <strong>{POST_AUTHOR.name}</strong>
            <BadgeCheck size={15} className="x-verified" />
            <span className="x-handle">@{POST_AUTHOR.handle}</span>
            <span className="x-sep">·</span>
            <span className="x-time">now</span>
            <MoreHorizontal size={16} className="x-menu" />
          </header>

          <p className="x-text"><RichText text={post} /></p>

          <footer className="x-actions">
            <span className="x-act"><MessageCircle size={15} /></span>
            <span className="x-act"><Repeat2 size={15} /></span>
            <span className="x-act"><Heart size={15} /></span>
            <span className="x-act"><Eye size={15} /></span>
            <span className="x-act"><Bookmark size={15} /></span>
            <span className="x-act"><Share size={15} /></span>
          </footer>

          <div className="x-meta">
            <span className={over ? "over" : ""}>{post.length} / {X_LIMIT} characters</span>
            {remaining > 0 ? (
              <span>+{remaining} more post{remaining === 1 ? "" : "s"} in the exported thread</span>
            ) : null}
          </div>

          {/*
            X's official Web Intent: opens the composer with the post prefilled.
            No API key, no OAuth, no cost — and the operator still presses Post,
            which is the whole point of the review gate.
            Only offered when the post fits, because X refuses to prefill text
            that would exceed 280 characters and the operator would have to edit
            it by hand anyway.
          */}
          {!over && post ? (
            <div className="x-handoff">
              <a
                className="x-open"
                href={`https://x.com/intent/tweet?text=${encodeURIComponent(post)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink size={13} /> Open in X to post
              </a>
              <CopyToClipboard text={tweets.join("\n\n")} label="Copy full thread" />
            </div>
          ) : null}
        </div>
      </article>
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
