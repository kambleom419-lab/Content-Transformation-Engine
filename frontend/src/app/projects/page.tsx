import { AppSidebar } from "@/components/app-sidebar";
import { RoutePlaceholder } from "@/components/route-placeholder";

export default function ProjectsPage() {
  return <main className="dashboard-shell"><AppSidebar /><section className="main-area"><RoutePlaceholder /></section></main>;
}
