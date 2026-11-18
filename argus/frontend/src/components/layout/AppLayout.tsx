import { clsx } from "clsx";
import {
  Activity,
  Briefcase,
  Building2,
  FlaskConical,
  LayoutDashboard,
  Pause,
  Play,
  SlidersHorizontal,
  UserRound,
} from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useHealth, useSetPaused, useSystemState } from "@/api/queries";
import { Button } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/preferences", label: "Preferences", icon: SlidersHorizontal },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/llm-lab", label: "LLM Lab", icon: FlaskConical },
];

function StatusDot({ ok, label, detail }: { ok: boolean | undefined; label: string; detail?: string | null }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-500" title={detail ?? undefined}>
      <span className={clsx("size-2 rounded-full", ok === undefined ? "bg-slate-400" : ok ? "bg-emerald-500" : "bg-red-500")} />
      {label}
    </span>
  );
}

export function AppLayout() {
  const health = useHealth();
  const system = useSystemState();
  const setPaused = useSetPaused();
  const toast = useToast();
  const paused = system.data?.paused ?? false;

  const togglePause = () =>
    setPaused.mutate(!paused, {
      onSuccess: (s) => toast.info(s.paused ? "Automation paused" : "Automation resumed"),
      onError: toast.error,
    });

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-5 md:flex dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-6 flex items-center gap-2 px-2">
          <img src="/favicon.svg" alt="" className="size-7" />
          <div>
            <p className="text-sm font-bold tracking-wide">ARGUS</p>
            <p className="text-[11px] text-slate-500">100 eyes · one career</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium",
                  isActive
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-1 px-2 text-xs">
          <StatusDot ok={health.data?.database.ok} label="Database" detail={health.data?.database.detail} />
          <StatusDot ok={health.data?.llm.ok} label="Local LLM" detail={health.data?.llm.detail} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-6 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
          <nav className="flex gap-1 overflow-x-auto md:hidden" aria-label="Main (mobile)">
            {NAV.map(({ to, label, end }) => (
              <NavLink key={to} to={to} end={end} className="rounded-md px-2 py-1 text-xs font-medium">
                {label}
              </NavLink>
            ))}
          </nav>
          <p className="hidden text-sm text-slate-500 md:block">
            {paused ? "Automation is paused — no background tasks will run." : "Running locally · your data stays on this machine"}
          </p>
          <Button
            variant={paused ? "primary" : "secondary"}
            size="sm"
            icon={paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
            loading={setPaused.isPending}
            onClick={togglePause}
            title="Global kill switch for all automation"
          >
            {paused ? "Resume" : "Pause all"}
          </Button>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
