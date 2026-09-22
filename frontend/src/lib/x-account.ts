"use client";

import { useSyncExternalStore } from "react";

/**
 * The operator's X account, remembered in this browser.
 *
 * X is published to through its Web Intent (`x.com/intent/tweet`), which opens
 * the composer signed in as whatever account the browser already has. No token
 * is stored here and nothing is posted automatically — this only remembers which
 * handle the operator says is theirs, so the preview and the hand-off agree.
 */

const X_ACCOUNT_KEY = "cte:x-account";
const X_ACCOUNT_EVENT = "cte:x-account-change";

/** Accept "@handle", "handle", or a full profile URL; return the bare handle. */
export function normalizeXHandle(value: string): string {
  return value
    .trim()
    .replace(/^https?:\/\/(www\.)?(x|twitter)\.com\//i, "")
    .replace(/^@+/, "")
    .split(/[/?#]/)[0]
    .trim();
}

function readXAccount(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(X_ACCOUNT_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeXAccount(value: string): void {
  if (typeof window === "undefined") return;
  try {
    if (value) window.localStorage.setItem(X_ACCOUNT_KEY, value);
    else window.localStorage.removeItem(X_ACCOUNT_KEY);
  } catch {
    /* storage unavailable — the account just is not remembered */
  }
  window.dispatchEvent(new Event(X_ACCOUNT_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(X_ACCOUNT_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(X_ACCOUNT_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** The saved X account, kept in sync across the dashboard and the preview. */
export function useXAccount(): [string, (value: string) => void] {
  const account = useSyncExternalStore(subscribe, readXAccount, () => "");
  return [account, writeXAccount];
}
