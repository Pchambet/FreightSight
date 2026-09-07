"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, btnSecondary, input, label } from "@/components/layout/AppShell";
import { updateContainer } from "@/features/actions";
import type { ContainerResponse } from "@/lib/api/client";
import { MILESTONES, MILESTONE_LABEL, type ContainerMilestone } from "@/lib/domain";
import { dateShort } from "@/lib/format";

function toDateInput(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "";
}

export default function TrackingPanel({ container }: { container: ContainerResponse }) {
  const [milestone, setMilestone] = useState<ContainerMilestone>(container.milestone);
  const [discharged, setDischarged] = useState(toDateInput(container.discharged_at));
  const [freeDays, setFreeDays] = useState(container.free_days_demurrage?.toString() ?? "");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const save = () =>
    startTransition(async () => {
      const result = await updateContainer(container.id, {
        milestone,
        discharged_at: discharged ? `${discharged}T12:00:00Z` : null,
        free_days_demurrage: freeDays === "" ? null : Number(freeDays),
      });
      if (!result.ok) return void toast.error(result.error);
      toast.success("Tracking updated");
      router.refresh();
    });

  return (
    <Card title="Tracking" right={<span className="text-xs text-slate-400">manual until a provider is connected</span>}>
      <div className="p-5 space-y-4">
        <div>
          <label className={label} htmlFor="milestone">Milestone</label>
          <select id="milestone" value={milestone} onChange={(e) => setMilestone(e.target.value as ContainerMilestone)} className={input}>
            {MILESTONES.map((m) => <option key={m} value={m}>{MILESTONE_LABEL[m]}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={label} htmlFor="discharged">Discharged on</label>
            <input id="discharged" type="date" value={discharged} onChange={(e) => setDischarged(e.target.value)} className={input} />
          </div>
          <div>
            <label className={label} htmlFor="freedays">Free days (demurrage)</label>
            <input id="freedays" type="number" min={0} max={60} placeholder="org default" value={freeDays} onChange={(e) => setFreeDays(e.target.value)} className={input} />
          </div>
        </div>
        <dl className="text-xs text-slate-500 grid grid-cols-2 gap-x-3 gap-y-1">
          <dt>ETA</dt><dd className="text-slate-700">{dateShort(container.eta)}</dd>
          <dt>Arrived</dt><dd className="text-slate-700">{dateShort(container.ata)}</dd>
          <dt>Gate out</dt><dd className="text-slate-700">{dateShort(container.gate_out_at)}</dd>
          <dt>Last free day</dt><dd className="text-slate-700">{dateShort(container.last_free_day)}</dd>
        </dl>
        <button type="button" onClick={save} disabled={pending} className={btnSecondary}>Save tracking</button>
      </div>
    </Card>
  );
}
