import { clsx } from "clsx";
import { useState } from "react";

import type { Schemas } from "@/api/client";
import { useAuditEvents, useTasks } from "@/api/queries";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui/primitives";
import { formatDate, timeAgo } from "@/lib/format";

type Status = Schemas["TaskOut"]["status"];
const STATUSES: Array<Status | undefined> = [undefined, "queued", "running", "succeeded", "failed"];
const TONE = { succeeded: "green", failed: "red", running: "blue", queued: "neutral", cancelled: "amber" } as const;

export function ActivityPage() {
  const [status, setStatus] = useState<Status | undefined>(undefined);
  const tasks = useTasks(status);
  const audit = useAuditEvents();
  const events = audit.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader title="Activity" description="Everything ARGUS does is recorded here — background tasks and an audit trail of every action." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Background tasks"
          description="Run by the worker (make worker). Refreshes every 3 s."
          actions={
            <div className="flex gap-1">
              {STATUSES.map((s) => (
                <button key={s ?? "all"} onClick={() => setStatus(s)} className={clsx("rounded-md px-2 py-1 text-xs font-medium", status === s ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}>
                  {s ?? "all"}
                </button>
              ))}
            </div>
          }
        >
          {tasks.isLoading ? <Spinner /> : !tasks.data?.items.length ? <EmptyState title="No tasks" /> : (
            <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {tasks.data.items.map((t) => (
                <li key={t.id} className="py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">#{t.id} {t.kind}</span>
                    <span className="flex items-center gap-2 text-xs text-slate-500">
                      {timeAgo(t.created_at)} <Badge tone={TONE[t.status]}>{t.status}</Badge>
                    </span>
                  </div>
                  {t.last_error && <p className="mt-1 text-xs text-red-600">{t.last_error}</p>}
                  {t.result && <p className="mt-1 truncate font-mono text-[11px] text-slate-500">{JSON.stringify(t.result)}</p>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Audit trail" description="Append-only. Personal values are never stored here — only which fields changed.">
          {audit.isLoading ? <Spinner /> : !events.length ? <EmptyState title="No events" /> : (
            <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {events.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-2 py-2">
                  <div>
                    <span className="font-medium">{e.action}</span>
                    {e.entity_type && <span className="text-xs text-slate-500"> · {e.entity_type} #{e.entity_id}</span>}
                    {Object.keys(e.details).length > 0 && <p className="truncate font-mono text-[11px] text-slate-500">{JSON.stringify(e.details)}</p>}
                  </div>
                  <span className="shrink-0 text-xs text-slate-500" title={formatDate(e.occurred_at)}>
                    <Badge tone={e.actor === "user" ? "violet" : "blue"}>{e.actor}</Badge> {timeAgo(e.occurred_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {audit.hasNextPage && <div className="mt-3 text-center"><Button size="sm" onClick={() => audit.fetchNextPage()} loading={audit.isFetchingNextPage}>Load more</Button></div>}
        </Card>
      </div>
    </>
  );
}
