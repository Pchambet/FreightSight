"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { deleteCost } from "@/features/actions";
import type { LandedCostReport } from "@/lib/api/client";
import { COST_TYPE_LABEL, METHOD_LABEL, SCOPE_LABEL } from "@/lib/domain";
import { dateShort } from "@/lib/format";

export default function CostLedger({ report, currency, revalidate }: { report: LandedCostReport; currency: string; revalidate: string }) {
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const remove = (id: string) =>
    startTransition(async () => {
      const result = await deleteCost(id, revalidate);
      if (!result.ok) return void toast.error(result.error);
      toast.success("Cost deleted");
      router.refresh();
    });

  return (
    <Card title="Costs" right={<span className="text-xs text-slate-500">{report.costs.length} recorded</span>}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className={th}>Date</th>
              <th className={th}>Type</th>
              <th className={th}>Scope</th>
              <th className={thRight}>Amount</th>
              <th className={thRight}>In {currency}</th>
              <th className={th}>Method</th>
              <th className={th}>Vendor / invoice</th>
              <th className={th}></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {report.costs.length === 0 ? (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-sm text-slate-500">No cost recorded yet.</td></tr>
            ) : (
              report.costs.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className={`${td} text-slate-600`}>{dateShort(c.cost_date)}</td>
                  <td className={td}>{COST_TYPE_LABEL[c.cost_type]}</td>
                  <td className={`${td} text-slate-600`}>{SCOPE_LABEL[c.scope]}</td>
                  <td className={tdRight}><Money amount={c.amount} currency={c.currency} /></td>
                  <td className={tdRight}>
                    <Money amount={c.amount_base} currency={currency} className="font-medium" />
                    {c.currency !== currency ? <div className="text-xs text-slate-400">@ {c.fx_rate} ({c.fx_source})</div> : null}
                  </td>
                  <td className={`${td} text-slate-600`}>{METHOD_LABEL[c.allocation_method]}</td>
                  <td className={`${td} text-slate-600 text-xs`}>{[c.vendor, c.invoice_number].filter(Boolean).join(" · ") || "—"}</td>
                  <td className={td}>
                    <button type="button" disabled={pending} onClick={() => remove(c.id)} className="text-slate-400 hover:text-red-600" aria-label="Delete cost"><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
