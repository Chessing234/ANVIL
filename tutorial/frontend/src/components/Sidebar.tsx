import { Activity, Award, BookOpen, Laptop, LayoutDashboard, Radar, Settings2, UserRound } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive ? "bg-slate-800 text-emerald-300" : "text-slate-400 hover:bg-slate-900 hover:text-slate-100",
  );

const learnLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive ? "bg-indigo-800/80 text-fuchsia-100" : "text-indigo-200/80 hover:bg-indigo-950/80 hover:text-indigo-50",
  );

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-800 bg-slate-950/95 backdrop-blur">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300">
          <Radar className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold tracking-tight">TUTORIAL SOC</div>
          <div className="text-xs text-slate-500">FIND EVIL! Ops</div>
        </div>
      </div>
      <Separator />
      <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wider text-indigo-300/70">Learning</div>
      <nav className="flex flex-col gap-1 p-3 pt-1">
        <NavLink to="/learn" className={learnLinkClass}>
          <BookOpen className="h-4 w-4" />
          Learn
        </NavLink>
        <NavLink to="/sandbox" className={learnLinkClass}>
          <Laptop className="h-4 w-4" />
          Sandbox
        </NavLink>
        <NavLink to="/profile" className={learnLinkClass}>
          <UserRound className="h-4 w-4" />
          Profile
        </NavLink>
        <NavLink to="/credentials" className={learnLinkClass}>
          <Award className="h-4 w-4" />
          Credentials
        </NavLink>
      </nav>
      <Separator />
      <nav className="flex flex-1 flex-col gap-1 p-3">
        <NavLink to="/" end className={linkClass}>
          <LayoutDashboard className="h-4 w-4" />
          Dashboard
        </NavLink>
        <NavLink to="/incidents" className={linkClass}>
          <Activity className="h-4 w-4" />
          Incidents
        </NavLink>
        <NavLink to="/settings" className={linkClass}>
          <Settings2 className="h-4 w-4" />
          Settings
        </NavLink>
      </nav>
      <div className="border-t border-slate-800 p-4 text-xs text-slate-500">
        Splunk · UiPath · LangGraph-ready telemetry surface.
      </div>
    </aside>
  );
}
