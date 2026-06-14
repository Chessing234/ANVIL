import { Outlet, useLocation } from "react-router-dom";

import { Header } from "@/components/Header";
import { Sidebar } from "@/components/Sidebar";
import { cn } from "@/lib/utils";

export function Layout() {
  const loc = useLocation();
  const edu =
    loc.pathname.startsWith("/learn") ||
    loc.pathname.startsWith("/sandbox") ||
    loc.pathname.startsWith("/profile") ||
    loc.pathname.startsWith("/credentials");

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col pl-60">
        <Header />
        <main
          className={cn(
            "flex-1 overflow-y-auto p-6",
            edu && "bg-gradient-to-b from-slate-950 via-indigo-950/25 to-slate-950 text-indigo-50",
          )}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
