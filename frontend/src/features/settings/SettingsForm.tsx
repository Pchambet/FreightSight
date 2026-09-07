"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, btnPrimary, input, label } from "@/components/layout/AppShell";
import { updateOrganization } from "@/features/actions";
import type { OrganizationResponse } from "@/lib/api/client";
import { METHOD_LABEL, USER_METHODS } from "@/lib/domain";

export default function SettingsForm({ org }: { org: OrganizationResponse }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    startTransition(async () => {
      const result = await updateOrganization({
        name: String(f.get("name") ?? org.name),
        base_currency: String(f.get("base_currency") ?? org.base_currency).toUpperCase(),
        default_allocation_method: String(f.get("default_allocation_method") ?? org.default_allocation_method),
        free_days_demurrage: Number(f.get("free_days_demurrage") ?? org.free_days_demurrage),
        free_days_detention: Number(f.get("free_days_detention") ?? org.free_days_detention),
      });
      if (!result.ok) return void toast.error(result.error);
      toast.success("Settings saved");
      router.refresh();
    });
  };

  return (
    <form onSubmit={submit} className="space-y-6 max-w-2xl">
      <Card title="Organization">
        <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className={label} htmlFor="name">Name</label>
            <input id="name" name="name" defaultValue={org.name} required className={input} />
          </div>
          <div>
            <label className={label} htmlFor="base_currency">Base currency</label>
            <input id="base_currency" name="base_currency" defaultValue={org.base_currency} maxLength={3} className={`${input} font-mono uppercase`} />
            <p className="text-xs text-slate-500 mt-1">Every landed cost is reported in this currency. Changing it does not restate existing rates.</p>
          </div>
        </div>
      </Card>
      <Card title="Allocation">
        <div className="p-5 space-y-3">
          <div>
            <label className={label} htmlFor="default_allocation_method">Default method for new costs</label>
            <select id="default_allocation_method" name="default_allocation_method" defaultValue={org.default_allocation_method} className={input}>
              {USER_METHODS.map((m) => <option key={m} value={m}>{METHOD_LABEL[m]}</option>)}
            </select>
          </div>
          <p className="text-xs text-slate-500">Freight is usually allocated by volume for FCL and by weight for air or LCL; insurance and duty by value. Customs duty always uses the CIF basis.</p>
        </div>
      </Card>
      <Card title="Free time">
        <div className="p-5 grid grid-cols-2 gap-4">
          <div>
            <label className={label} htmlFor="free_days_demurrage">Demurrage free days</label>
            <input id="free_days_demurrage" name="free_days_demurrage" type="number" min={0} max={60} defaultValue={org.free_days_demurrage} className={input} />
          </div>
          <div>
            <label className={label} htmlFor="free_days_detention">Detention free days</label>
            <input id="free_days_detention" name="free_days_detention" type="number" min={0} max={60} defaultValue={org.free_days_detention} className={input} />
          </div>
          <p className="col-span-2 text-xs text-slate-500">Calendar days from discharge. Override per container when the carrier or terminal differs.</p>
        </div>
      </Card>
      <button type="submit" disabled={pending} className={btnPrimary}>Save settings</button>
    </form>
  );
}
