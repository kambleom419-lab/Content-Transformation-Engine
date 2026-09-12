"use client";

import { usePathname } from "next/navigation";

const labels: Record<string, string> = {
  "/projects": "Projects",
  "/templates": "Templates",
  "/history": "History",
  "/settings": "Settings",
};

export function RoutePlaceholder() {
  const pathname = usePathname();
  const title = labels[pathname] ?? "Workspace";
  return (
    <div className="route-placeholder">
      <p className="eyebrow">Workspace</p>
      <h1>{title}</h1>
      <p>This workspace is ready for your team&apos;s {title.toLowerCase()}.</p>
    </div>
  );
}
